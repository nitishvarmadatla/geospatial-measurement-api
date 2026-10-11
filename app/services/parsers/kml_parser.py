"""Safe KML parser extracting Placemark geometries, holes, and attributes."""
import re
from typing import Any, Dict, List, Optional, Tuple
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from shapely.geometry import (
    Point,
    LineString,
    Polygon,
    MultiPolygon,
    MultiLineString,
    MultiPoint,
    GeometryCollection,
)
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import InvalidKmlError
from app.core.logging import logger
from app.services.parsers.base import BaseParser, ParsedDataset, ParsedFeature


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from tag."""
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_coord_tuple(coord_str: str) -> Optional[Tuple[float, float]]:
    """Parse 'lon,lat[,alt]' string into (lon, lat) float tuple."""
    parts = coord_str.strip().split(",")
    if len(parts) >= 2:
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None
    return None


def _parse_coordinates_block(text: Optional[str]) -> List[Tuple[float, float]]:
    """Parse whitespace-separated coordinate list."""
    if not text:
        return []
    coords: List[Tuple[float, float]] = []
    # Split by whitespace, newline, or tab
    tokens = re.split(r"[\s\r\n\t]+", text.strip())
    for token in tokens:
        if token:
            pt = _parse_coord_tuple(token)
            if pt is not None:
                coords.append(pt)
    return coords


def _parse_linear_ring(elem: Element) -> List[Tuple[float, float]]:
    """Extract coordinates from a LinearRing element."""
    for child in elem:
        if _strip_ns(child.tag).lower() == "coordinates":
            return _parse_coordinates_block(child.text)
    return []


def _parse_polygon_elem(poly_elem: Element) -> Optional[Polygon]:
    """Parse a KML Polygon element, extracting outer boundary and all interior holes."""
    outer_coords: List[Tuple[float, float]] = []
    holes: List[List[Tuple[float, float]]] = []

    for child in poly_elem:
        tag = _strip_ns(child.tag).lower()
        if tag == "outerboundaryis":
            for ring in child:
                if _strip_ns(ring.tag).lower() == "linearring":
                    outer_coords = _parse_linear_ring(ring)
        elif tag == "innerboundaryis":
            for ring in child:
                if _strip_ns(ring.tag).lower() == "linearring":
                    hole_coords = _parse_linear_ring(ring)
                    if len(hole_coords) >= 3:
                        holes.append(hole_coords)

    if len(outer_coords) < 3:
        return None

    try:
        return Polygon(shell=outer_coords, holes=holes)
    except Exception as e:
        logger.warning(f"Error constructing Polygon: {e}")
        return None


def _parse_linestring_elem(elem: Element) -> Optional[LineString]:
    """Parse a KML LineString element."""
    for child in elem:
        if _strip_ns(child.tag).lower() == "coordinates":
            coords = _parse_coordinates_block(child.text)
            if len(coords) >= 2:
                try:
                    return LineString(coords)
                except Exception:
                    return None
    return None


def _parse_point_elem(elem: Element) -> Optional[Point]:
    """Parse a KML Point element."""
    for child in elem:
        if _strip_ns(child.tag).lower() == "coordinates":
            coords = _parse_coordinates_block(child.text)
            if len(coords) >= 1:
                try:
                    return Point(coords[0])
                except Exception:
                    return None
    return None


def _parse_geometry_element(elem: Element) -> Optional[BaseGeometry]:
    """Recursively parse KML geometry elements."""
    tag = _strip_ns(elem.tag).lower()

    if tag == "polygon":
        return _parse_polygon_elem(elem)
    elif tag == "linestring":
        return _parse_linestring_elem(elem)
    elif tag == "point":
        return _parse_point_elem(elem)
    elif tag == "multigeometry":
        sub_geoms: List[BaseGeometry] = []
        for child in elem:
            sub = _parse_geometry_element(child)
            if sub is not None and not sub.is_empty:
                sub_geoms.append(sub)

        if not sub_geoms:
            return None

        # Check homogeneous sub-geometries
        all_polygons = all(isinstance(g, Polygon) for g in sub_geoms)
        all_lines = all(isinstance(g, LineString) for g in sub_geoms)
        all_points = all(isinstance(g, Point) for g in sub_geoms)

        if all_polygons:
            return MultiPolygon(sub_geoms)
        elif all_lines:
            return MultiLineString(sub_geoms)
        elif all_points:
            return MultiPoint(sub_geoms)
        else:
            return GeometryCollection(sub_geoms)

    return None


class KmlParser(BaseParser):
    """Parser for KML 2.2 documents."""

    def parse(self, file_path: str) -> ParsedDataset:
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise InvalidKmlError(f"XML syntax error in KML file: {str(e)}")
        except Exception as e:
            raise InvalidKmlError(f"Failed to read KML document: {str(e)}")

        placemarks: List[Element] = []
        # Find all Placemark nodes anywhere in document
        for elem in root.iter():
            if _strip_ns(elem.tag).lower() == "placemark":
                placemarks.append(elem)

        features: List[ParsedFeature] = []
        feature_index = 0

        for pm in placemarks:
            pm_id = pm.attrib.get("id")
            name: Optional[str] = None
            description: Optional[str] = None
            properties: Dict[str, Any] = {}

            geom: Optional[BaseGeometry] = None

            for child in pm:
                child_tag = _strip_ns(child.tag).lower()
                if child_tag == "name":
                    name = child.text.strip() if child.text else None
                elif child_tag == "description":
                    description = child.text.strip() if child.text else None
                elif child_tag == "extendeddata":
                    for data_child in child:
                        data_tag = _strip_ns(data_child.tag).lower()
                        if data_tag == "data":
                            attr_name = data_child.attrib.get("name")
                            val_elem = None
                            for sub in data_child:
                                if _strip_ns(sub.tag).lower() == "value":
                                    val_elem = sub
                                    break
                            val = val_elem.text.strip() if val_elem is not None and val_elem.text else ""
                            if attr_name:
                                properties[attr_name] = val
                        elif data_tag == "simpledata":
                            attr_name = data_child.attrib.get("name")
                            val = data_child.text.strip() if data_child.text else ""
                            if attr_name:
                                properties[attr_name] = val
                else:
                    # Check if this child is a geometry element
                    candidate_geom = _parse_geometry_element(child)
                    if candidate_geom is not None:
                        geom = candidate_geom

            if name:
                properties["name"] = name
            if description:
                properties["description"] = description

            final_id = pm_id or name or f"placemark_{feature_index}"

            if geom is None:
                features.append(
                    ParsedFeature(
                        feature_index=feature_index,
                        feature_id=final_id,
                        geometry=None,
                        geometry_type="Unknown",
                        properties=properties,
                        is_empty=True,
                        is_valid=False,
                        error_message="No recognized geometry found in Placemark",
                    )
                )
            else:
                geom_type = geom.geom_type
                is_empty = geom.is_empty
                is_valid = geom.is_valid
                features.append(
                    ParsedFeature(
                        feature_index=feature_index,
                        feature_id=final_id,
                        geometry=geom,
                        geometry_type=geom_type,
                        properties=properties,
                        is_empty=is_empty,
                        is_valid=is_valid,
                    )
                )

            feature_index += 1

        return ParsedDataset(
            file_type="kml",
            crs="EPSG:4326",
            is_crs_uncertain=False,
            crs_raw="EPSG:4326",
            features=features,
            warnings=[],
        )
