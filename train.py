import os
import sys
import argparse
import shutil
import time
import csv
import json
import logging
from datetime import datetime
from pathlib import Path

# Add backend directory to sys.path to allow app imports
sys.path.append(str(Path(__file__).parent / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_pipeline")

# Safe imports for ultralytics and DB
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("ultralytics package is not installed. Training cannot run.")

import asyncio
from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.models import models
import dataset_pipeline

async def update_run_db(run_id: str, status: str, error_message: str = None, metrics: dict = None, model_version_id: str = None, dataset_size: int = None):
    """Utility to update the training run status and metrics in the SQLite/PostgreSQL database."""
    async with AsyncSessionLocal() as db:
        try:
            query = select(models.TrainingRun).where(models.TrainingRun.id == run_id)
            result = await db.execute(query)
            run = result.scalars().first()
            if run:
                run.status = status
                if error_message:
                    run.error_message = error_message
                if metrics:
                    run.metrics_json = metrics
                if model_version_id:
                    run.model_version_id = model_version_id
                if dataset_size:
                    run.dataset_size = dataset_size
                if status in ["completed", "failed"]:
                    run.completed_at = datetime.utcnow()
                await db.commit()
                logger.info(f"Updated database TrainingRun {run_id} to status: {status}")
        except Exception as e:
            logger.error(f"Failed to update TrainingRun in database: {e}")

async def create_new_run_db(epochs: int, batch_size: int, img_size: int) -> str:
    """Create a new training run record in the database if train.py was run manually."""
    async with AsyncSessionLocal() as db:
        try:
            run = models.TrainingRun(
                status="running",
                epochs=epochs,
                batch_size=batch_size,
                img_size=img_size,
                created_at=datetime.utcnow()
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            logger.info(f"Registered new TrainingRun {run.id} in database.")
            return run.id
        except Exception as e:
            logger.error(f"Failed to create training run in database: {e}")
            return "manual_run"

async def register_model_version_db(version_str: str, model_path: str, metrics: dict) -> str:
    """Registers the newly trained model version and sets it as the active verifier model."""
    async with AsyncSessionLocal() as db:
        try:
            # Set all other model versions to inactive
            await db.execute(
                update(models.ModelVersion)
                .where(models.ModelVersion.is_active == True)
                .values(is_active=False)
            )
            
            # Create new active model version
            mv = models.ModelVersion(
                version_str=version_str,
                model_path=model_path,
                precision=metrics.get("precision"),
                recall=metrics.get("recall"),
                map50=metrics.get("map50"),
                map50_95=metrics.get("map50_95"),
                is_active=True,
                created_at=datetime.utcnow()
            )
            db.add(mv)
            await db.commit()
            await db.refresh(mv)
            logger.info(f"Model version {version_str} successfully registered and activated in DB.")
            return mv.id
        except Exception as e:
            logger.error(f"Failed to register model version in DB: {e}")
            return None

def parse_metrics_csv(results_csv_path: Path) -> dict:
    """Parses YOLOv8 training results.csv to extract final performance metrics using the standard csv library."""
    metrics = {
        "precision": 0.0,
        "recall": 0.0,
        "map50": 0.0,
        "map50_95": 0.0
    }
    if not results_csv_path.exists():
        logger.warning(f"results.csv not found at {results_csv_path}. Default metrics will be reported.")
        return metrics
    
    try:
        with open(results_csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                return metrics
            
            final_row = rows[-1]
            # Strip key and value whitespaces
            cleaned_row = {k.strip(): v.strip() for k, v in final_row.items() if k is not None}
            
            metrics["precision"] = float(cleaned_row.get("metrics/precision(B)", 0.0))
            metrics["recall"] = float(cleaned_row.get("metrics/recall(B)", 0.0))
            metrics["map50"] = float(cleaned_row.get("metrics/mAP50(B)", 0.0))
            metrics["map50_95"] = float(cleaned_row.get("metrics/mAP50-95(B)", 0.0))
            
            logger.info(f"Parsed final metrics: Precision={metrics['precision']:.3f}, Recall={metrics['recall']:.3f}, mAP50={metrics['map50']:.3f}")
    except Exception as e:
        logger.error(f"Error parsing training CSV results: {e}")
        
    return metrics

def run_training_pipeline(epochs: int, batch: int, img_size: int, run_id: str = None, device: str = None, workers: int = 4):
    if not YOLO_AVAILABLE:
        raise ImportError("ultralytics YOLO package is required to run training.")

    # 1. Initialize dataset structure and populate if empty
    logger.info("Initializing dataset split...")
    success = dataset_pipeline.run_pipeline()
    if not success:
        raise ValueError("Dataset pipeline failed. Cannot train.")

    # Get dataset size
    dataset_report_path = Path("datasets/dataset_report.json")
    dataset_size = 0
    if dataset_report_path.exists():
        try:
            with open(dataset_report_path, "r") as f:
                rep = json.load(f)
                dataset_size = rep.get("total_valid_images", 0)
        except Exception:
            pass

    # Create run loop
    loop = asyncio.get_event_loop()

    if not run_id:
        # Create run in DB if running script directly
        run_id = loop.run_until_complete(create_new_run_db(epochs, batch, img_size))

    # Mark run as running in DB
    loop.run_until_complete(update_run_db(run_id, "running", dataset_size=dataset_size))

    # Determine and normalize device choice.
    # Accepts: None/"auto" (auto-detect), "gpu"/"cuda"/"0" (force GPU), "cpu" (force CPU).
    import torch
    cuda_ok = torch.cuda.is_available()
    choice = (device or "auto").lower()
    if choice in ("gpu", "cuda", "0"):
        if cuda_ok:
            device = "0"
        else:
            logger.warning("GPU requested but CUDA is not available. Falling back to CPU.")
            device = "cpu"
    elif choice == "cpu":
        device = "cpu"
    else:  # auto
        device = "0" if cuda_ok else "cpu"

    if device == "0":
        logger.info(f"Starting training on GPU: {torch.cuda.get_device_name(0)} (device 0)")
    else:
        logger.info("Starting training on CPU.")

    # Define paths
    yaml_path = Path("datasets/dataset.yaml").resolve()
    
    # We clean up standard ultralytics run folders or target a specific folder name to ensure consistency
    project_dir = Path("backend/uploads/models")
    project_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_str = f"v_{timestamp}"
    run_name = f"train_{version_str}"

    try:
        # 2. Initialize model (yolov8s pre-trained or empty)
        logger.info("Loading pre-trained YOLOv8s model weights...")
        model = YOLO("yolov8s.pt")

        # 3. Train
        # Save results inside backend/uploads/models/<run_name>
        # 3. Train
        # Save results inside backend/uploads/models/<run_name>
        logger.info(f"Launching YOLOv8 training loop (epochs={epochs}, batch={batch}, imgsz={img_size}, workers={workers})...")
        results = model.train(
            data=str(yaml_path),
            epochs=epochs,
            batch=batch,
            imgsz=img_size,
            device=device,
            project=str(project_dir.resolve()),
            name=run_name,
            verbose=True,
            val=True,
            workers=workers,  # fewer parallel image decoders -> avoids host RAM OOM on high-res photos
            cache=False       # never cache full-res images in RAM
        )

        logger.info("Training complete. Collecting artifacts...")

        # 4. Save and copy checkpoints/artifacts
        save_dir = Path(model.trainer.save_dir) if (hasattr(model, "trainer") and model.trainer) else (project_dir / run_name)
        best_weights = save_dir / "weights" / "best.pt"
        results_csv = save_dir / "results.csv"

        if not best_weights.exists():
            raise FileNotFoundError(f"Training did not produce best.pt checkpoint at {best_weights}")

        # Parse metrics
        metrics = parse_metrics_csv(results_csv)

        # Register model version and activate it
        mv_id = loop.run_until_complete(register_model_version_db(
            version_str=version_str,
            model_path=str(best_weights.resolve()),
            metrics=metrics
        ))

        # Update dynamic verifier singleton to load new weights immediately!
        try:
            from app.services.ai_verifier import ai_verifier
            ai_verifier.load_model(str(best_weights.resolve()))
            logger.info("Dynamic AI Verifier updated to use newly trained model weights.")
        except Exception as e:
            logger.error(f"Failed to hot-swap active model verifier weights: {e}")

        # Update run status
        loop.run_until_complete(update_run_db(
            run_id=run_id,
            status="completed",
            metrics=metrics,
            model_version_id=mv_id
        ))

        logger.info(f"Training pipeline finished successfully! Model version is {version_str}.")

    except Exception as e:
        logger.error(f"Training failed with exception: {e}")
        loop.run_until_complete(update_run_db(
            run_id=run_id,
            status="failed",
            error_message=str(e)
        ))
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CXR-AIM YOLOv8s Training Pipeline")
    parser.add_argument("--epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--img-size", type=int, default=640, help="Input image dimension size")
    parser.add_argument("--run-id", type=str, default=None, help="Database training run ID")
    parser.add_argument("--device", type=str, default="auto",
                        help="Training device: 'auto' (GPU if available), 'gpu'/'cuda'/'0' (force GPU), or 'cpu'")
    parser.add_argument("--workers", type=int, default=4,
                        help="Dataloader workers. Lower this (e.g. 2) if you hit out-of-memory on high-res images.")

    args = parser.parse_args()

    # Run the main training procedure
    run_training_pipeline(
        epochs=args.epochs,
        batch=args.batch,
        img_size=args.img_size,
        run_id=args.run_id,
        device=args.device,
        workers=args.workers
    )
