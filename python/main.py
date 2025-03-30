import os
import logging
import pathlib
import json
import hashlib
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Path
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Define paths
BASE_DIR = pathlib.Path(__file__).parent.resolve()
IMAGES_DIR = BASE_DIR / "images"
DB_PATH = BASE_DIR / "db" / "mercari.sqlite3"
ITEMS_JSON = BASE_DIR / "items.json"

# Ensure directories exist
IMAGES_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

# Setup logger
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.INFO)

# CORS Middleware
origins = [os.environ.get("FRONT_URL", "http://localhost:3000")]
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

class Item(BaseModel):
    name: str
    category: str
    image_name: str = None 

class HelloResponse(BaseModel):
    message: str

@app.get("/", response_model=HelloResponse)
def hello():
    return {"message": "Hello, world!"}


# Read Items
def read_items():
    if not ITEMS_JSON.exists()or ITEMS_JSON.stat().st_size == 0:
        return {"items": []}
    with open(ITEMS_JSON, "r") as file:
        try:
            return json.load(file)
        except json.JSONDecodeError:
            return {"items": []}

# Save Items
def save_items(data):
    with open(ITEMS_JSON, "w") as file:
        json.dump(data, file, indent=4)


@app.post("/items")
async def add_item(
    name: str = Form(...),
    category: str = Form(...),
    image: UploadFile = File(...)
):
    data = read_items()

    # Hash Image Name
    image_bytes = await image.read()
    image_hash = hashlib.sha256(image_bytes).hexdigest()
    image_filename = f"{image_hash}.jpg"

    # Save Image
    image_path = IMAGES_DIR / image_filename
    with open(image_path, "wb") as img_file:
        img_file.write(image_bytes)

    # Add Item
    new_item = {"name": name, "category": category, "image_name": image_filename}
    data["items"].append(new_item)
    save_items(data)

    return {"message": "Item added successfully!", "item": new_item}

@app.get("/items")
def get_items():
    return read_items()

@app.get("/items/{item_id}")
def get_item(item_id: int = Path(..., description="The ID of the item (1-based index)")):
    data = read_items()

    if item_id < 1 or item_id > len(data["items"]):
        raise HTTPException(status_code=404, detail="Item not found")

    return data["items"][item_id - 1]

@app.get("/images/{image_name}")
async def get_image(image_name: str):
    image_path = IMAGES_DIR / image_name

    if not image_name.endswith(".jpg"):
        raise HTTPException(status_code=400, detail="Only .jpg images are supported.")

    if not image_path.exists():
        logger.debug(f"Image not found: {image_path}")
        return FileResponse(IMAGES_DIR / "default.jpg")

    return FileResponse(image_path)
