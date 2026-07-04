import os
import shutil
import random
import yaml
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple, Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dataset_pipeline")

# Configuration Paths
DATASET_ROOT = Path("D:/CXR_AIM/dataset")
OUTPUT_ROOT = Path("D:/CXR_AIM/datasets")

SPLIT_DIRS = {
    "train": {
        "images": OUTPUT_ROOT / "images" / "train",
        "labels": OUTPUT_ROOT / "labels" / "train"
    },
    "val": {
        "images": OUTPUT_ROOT / "images" / "val",
        "labels": OUTPUT_ROOT / "labels" / "val"
    },
    "test": {
        "images": OUTPUT_ROOT / "images" / "test",
        "labels": OUTPUT_ROOT / "labels" / "test"
    }
}

CLASS_MAP = {
    0: "hole"
}

def setup_directories():
    """Create directory structure for YOLO dataset."""
    logger.info("Initializing datasets directory structure...")
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    for split, subdirs in SPLIT_DIRS.items():
        subdirs["images"].mkdir(parents=True, exist_ok=True)
        subdirs["labels"].mkdir(parents=True, exist_ok=True)

def parse_voc_xml(xml_path: Path) -> Tuple[int, int, List[Tuple[int, float, float, float, float]]]:
    """
    Parses Pascal VOC XML file and converts bounding boxes for class 'hole' to YOLO normalized format.
    Returns: (width, height, list of annotations: (class_id, x_center, y_center, w, h))
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        
        size_elem = root.find("size")
        if size_elem is None:
            return 0, 0, []
            
        width = int(size_elem.find("width").text)
        height = int(size_elem.find("height").text)
        
        if width <= 0 or height <= 0:
            return 0, 0, []
            
        annotations = []
        for obj in root.findall("object"):
            name = obj.find("name").text.strip().lower()
            # Train ONLY 'hole' class
            if name != "hole":
                continue
                
            bndbox = obj.find("bndbox")
            if bndbox is None:
                continue
                
            xmin = float(bndbox.find("xmin").text)
            ymin = float(bndbox.find("ymin").text)
            xmax = float(bndbox.find("xmax").text)
            ymax = float(bndbox.find("ymax").text)
            
            # Convert to YOLO coordinates normalized to [0.0, 1.0]
            x_center = (xmin + xmax) / 2.0 / width
            y_center = (ymin + ymax) / 2.0 / height
            w_norm = (xmax - xmin) / width
            h_norm = (ymax - ymin) / height
            
            # Clip bounds to [0, 1]
            x_center = min(max(x_center, 0.0), 1.0)
            y_center = min(max(y_center, 0.0), 1.0)
            w_norm = min(max(w_norm, 0.0), 1.0)
            h_norm = min(max(h_norm, 0.0), 1.0)
            
            # Class ID for 'hole' is 0
            annotations.append((0, x_center, y_center, w_norm, h_norm))
            
        return width, height, annotations
    except Exception as e:
        logger.error(f"Error parsing XML file {xml_path}: {e}")
        return 0, 0, []

def scan_and_match_dataset() -> List[Tuple[Path, Path]]:
    """
    Recursively scans the DATASET_ROOT for XML files and matches them with corresponding image files.
    Returns list of tuples (image_path, xml_path)
    """
    logger.info(f"Scanning dataset root recursively: {DATASET_ROOT}")
    matched_pairs = []
    
    if not DATASET_ROOT.exists():
        logger.error(f"Dataset root directory {DATASET_ROOT} does not exist.")
        return []
        
    xml_files = list(DATASET_ROOT.rglob("*.xml"))
    logger.info(f"Found {len(xml_files)} XML annotation files.")
    
    image_extensions = [".jpg", ".jpeg", ".png"]
    
    for xml_path in xml_files:
        matched = False
        for ext in image_extensions:
            img_path = xml_path.with_suffix(ext)
            if img_path.exists():
                matched_pairs.append((img_path, xml_path))
                matched = True
                break
        if not matched:
            # Try case-insensitive check if OS has specific extension naming
            for item in xml_path.parent.iterdir():
                if item.is_file() and item.stem == xml_path.stem and item.suffix.lower() in image_extensions:
                    matched_pairs.append((item, xml_path))
                    matched = True
                    break
            if not matched:
                logger.warning(f"No matching image found for XML: {xml_path.name}")
                
    logger.info(f"Successfully matched {len(matched_pairs)} image/XML pairs.")
    return matched_pairs

def split_and_distribute(matched_pairs: List[Tuple[Path, Path]], train_ratio=0.7, val_ratio=0.2, test_ratio=0.1) -> Dict[str, List[Tuple[Path, Path]]]:
    """Splits dataset pairs into train, val, and test partitions, creating label text files and copying images."""
    logger.info(f"Splitting dataset into train={train_ratio}, val={val_ratio}, test={test_ratio}...")
    
    # Clean output directories first
    for split in SPLIT_DIRS:
        for folder in ["images", "labels"]:
            if SPLIT_DIRS[split][folder].exists():
                for item in SPLIT_DIRS[split][folder].iterdir():
                    if item.is_file():
                        item.unlink()
                        
    shuffled_pairs = list(matched_pairs)
    random.seed(42)
    random.shuffle(shuffled_pairs)
    
    total = len(shuffled_pairs)
    train_end = int(total * train_ratio)
    val_end = train_end + int(total * val_ratio)
    
    splits = {
        "train": shuffled_pairs[:train_end],
        "val": shuffled_pairs[train_end:val_end],
        "test": shuffled_pairs[val_end:]
    }
    
    for split_name, pairs in splits.items():
        logger.info(f"Processing split '{split_name}' containing {len(pairs)} pairs...")
        for img_path, xml_path in pairs:
            # Parse Pascal VOC XML
            w, h, annotations = parse_voc_xml(xml_path)
            
            # Destination file paths
            dest_img_path = SPLIT_DIRS[split_name]["images"] / img_path.name
            dest_lbl_path = SPLIT_DIRS[split_name]["labels"] / xml_path.with_suffix(".txt").name
            
            # Copy image file
            shutil.copy2(img_path, dest_img_path)
            
            # Write labels in YOLO format (even if empty, for background learning context)
            with open(dest_lbl_path, "w", encoding="utf-8") as f:
                for cls_id, cx, cy, box_w, box_h in annotations:
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {box_w:.6f} {box_h:.6f}\n")
                    
    logger.info("Dataset split and distribution complete.")
    return splits

def generate_dataset_yaml():
    """Generates the dataset.yaml file required by Ultralytics YOLOv8s."""
    yaml_path = OUTPUT_ROOT / "dataset.yaml"
    logger.info(f"Generating dataset configuration file at {yaml_path}...")
    
    data = {
        "path": str(OUTPUT_ROOT.resolve()).replace("\\", "/"),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": CLASS_MAP
    }
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        
    logger.info("dataset.yaml generated successfully.")

def generate_reports(splits: Dict[str, List[Tuple[Path, Path]]]):
    """Generates statistic summary and writes both dataset_report.json and dataset_report.md."""
    json_path = OUTPUT_ROOT / "dataset_report.json"
    md_path = OUTPUT_ROOT / "dataset_report.md"
    logger.info(f"Generating dataset statistics report at {json_path}...")
    
    total_images = sum(len(pairs) for pairs in splits.values())
    total_labels = 0
    split_counts = {}
    class_distribution = {"hole": 0}
    
    for split_name, pairs in splits.items():
        split_counts[split_name] = len(pairs)
        for _, xml_path in pairs:
            _, _, annotations = parse_voc_xml(xml_path)
            total_labels += len(annotations)
            class_distribution["hole"] += len(annotations)
            
    avg_holes = (total_labels / total_images) if total_images > 0 else 0.0
    
    stats = {
        "timestamp": os.path.getmtime(xml_path) if total_images > 0 else 0.0,
        "total_images": total_images,
        "total_labels": total_labels,
        "average_holes_per_image": avg_holes,
        "train_count": split_counts.get("train", 0),
        "val_count": split_counts.get("val", 0),
        "test_count": split_counts.get("test", 0),
        "class_distribution": class_distribution,
        
        # Keep keys for frontend dashboard compatibility
        "total_raw_images": total_images,
        "total_valid_images": total_images,
        "split_counts": split_counts,
        "class_counts": {
            "hole": total_labels,
            "bullet_hole": total_labels
        }
    }
    
    # Save JSON report
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)
        
    # Save Markdown report
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# CXR-AIM Local Dataset Analysis Report\n\n")
        f.write("This report provides a telemetry breakdown of the local Pascal VOC dataset loaded by the platform.\n\n")
        f.write("## Dataset Summary Metrics\n\n")
        f.write(f"- **Total Images Matched**: {total_images}\n")
        f.write(f"- **Total Hole Annotations**: {total_labels}\n")
        f.write(f"- **Average Holes Per Image**: {avg_holes:.2f}\n\n")
        
        f.write("## Data Partition Splits\n\n")
        f.write("| Partition | Image Count | Percentage |\n")
        f.write("| --- | --- | --- |\n")
        for split, count in split_counts.items():
            pct = (count / total_images * 100) if total_images > 0 else 0.0
            f.write(f"| {split.capitalize()} | {count} | {pct:.1f}% |\n")
            
        f.write("\n## Class Distributions (Class Map)\n\n")
        f.write("| Class Name | ID | Instance Count |\n")
        f.write("| --- | --- | --- |\n")
        f.write(f"| hole | 0 | {total_labels} |\n")
        
    logger.info("Dataset statistics reports created successfully.")

def run_pipeline() -> bool:
    """Run full dataset pipeline sequentially."""
    setup_directories()
    matched_pairs = scan_and_match_dataset()
    if not matched_pairs:
        logger.error("No valid matching XML/image pairs found in local dataset directory.")
        return False
        
    splits = split_and_distribute(matched_pairs)
    generate_dataset_yaml()
    generate_reports(splits)
    
    logger.info("Dataset migration pipeline ran successfully!")
    return True

if __name__ == "__main__":
    run_pipeline()
