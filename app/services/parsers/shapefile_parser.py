"""Shapefile parser using pure-Python pyshp, reading geometries, holes, attributes, and .prj."""
import os
from typing import Optional, Dict, Any
import shapefile
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from app.core.logging import logger
from app.services.parsers.base import BaseParser, ParsedDataset, ParsedFeature


class ShapefileParser(BaseParser):
    """Parser for ESRI Shapefile bundles (.shp, .shx, .dbf, and optional .prj)."""

    def __init__(self, prj_path: Optional[str] = None):
        self.prj_path = prj_path

    def parse(self, file_path: str) -> ParsedDataset:
        """Parse Shapefile given .shp file path."""
        warnings = []
        crs_raw: Optional[str] = None
        is_crs_uncertain = False
        crs_str = "UNKNOWN"

        # 1. Inspect .prj file
        actual_prj = self.prj_path
        if not actual_prj:
            base_no_ext = os.path.splitext(file_path)[0]
            candidate_prj = f"{base_no_ext}.prj"
            if os.path.exists(candidate_prj):
                actual_prj = candidate_prj

        if actual_prj and os.path.exists(actual_prj):
            try:
                with open(actual_prj, "r", encoding="utf-8", errors="ignore") as f_prj:
                    crs_raw = f_prj.read().strip()
                if crs_raw:
                    crs_str = crs_raw
                else:
                    is_crs_uncertain = True
                    crs_str = "UNKNOWN"
                    warnings.append("The .prj file is empty; CRS is uncertain.")
            except Exception as e:
                is_crs_uncertain = True
                crs_str = "UNKNOWN"
                warnings.append(f"Failed to read .prj file: {str(e)}")
        else:
            is_crs_uncertain = True
            crs_str = "UNKNOWN"
            warnings.append("Missing .prj file; CRS uncertainty prevents safe metric projection.")

        features = []
        try:
            with shapefile.Reader(file_path) as sf:
                for idx, sr in enumerate(sf.shapeRecords()):
                    # Extract properties
                    try:
                        raw_props = sr.record.as_dict()
                        # Convert any non-serializable objects (like bytes or dates)
                        props: Dict[str, Any] = {}
                        for k, v in raw_props.items():
                            if isinstance(v, bytes):
                                props[k] = v.decode("utf-8", errors="replace")
                            elif hasattr(v, "isoformat"):
                                props[k] = v.isoformat()
                            else:
                                props[k] = v
                    except Exception as e:
                        props = {"_parse_warning": f"Failed to extract DBF properties: {e}"}

                    # Determine Feature ID
                    feat_id = None
                    for candidate_id_key in ["id", "ID", "fid", "FID", "objectid", "OBJECTID", "gid", "GID"]:
                        if candidate_id_key in props and props[candidate_id_key] is not None:
                            feat_id = str(props[candidate_id_key])
                            break
                    if not feat_id:
                        feat_id = f"feature_{idx}"

                    # Extract geometry
                    geom: Optional[BaseGeometry] = None
                    geom_type = "Unknown"
                    is_empty = False
                    is_valid = True
                    err_msg = None

                    try:
                        shp_geom = sr.shape
                        if shp_geom.shapeType == shapefile.NULL or not shp_geom.points:
                            is_empty = True
                            geom_type = "Empty"
                        else:
                            geo_interface = shp_geom.__geo_interface__
                            geom = shape(geo_interface)
                            geom_type = geom.geom_type
                            is_empty = geom.is_empty
                            is_valid = geom.is_valid
                    except Exception as e:
                        err_msg = f"Failed to extract shape geometry: {str(e)}"
                        geom = None
                        geom_type = "CorruptGeometry"
                        is_valid = False

                    features.append(
                        ParsedFeature(
                            feature_index=idx,
                            feature_id=feat_id,
                            geometry=geom,
                            geometry_type=geom_type,
                            properties=props,
                            is_empty=is_empty,
                            is_valid=is_valid,
                            error_message=err_msg,
                        )
                    )
        except Exception as e:
            logger.error(f"Error opening Shapefile {file_path}: {e}")
            raise

        return ParsedDataset(
            file_type="shapefile",
            crs=crs_str,
            is_crs_uncertain=is_crs_uncertain,
            crs_raw=crs_raw,
            features=features,
            warnings=warnings,
        )
