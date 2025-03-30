import os
import hashlib
import logging
import sqlite3
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Path, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Database & Image Storage Paths
DB_FILE = "db/mercari.sqlite3"
IMAGE_DIR = "images"

# Ensure image directory exists
os.makedirs(IMAGE_DIR, exist_ok=True)

# Create FastAPI app
app = FastAPI()

# Allow CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection function
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# Pydantic model for Item
class Item(BaseModel):
    name: str
    category: str
    image_name: str = None

# Create tables if not exist
def create_tables():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER NOT NULL,
            image_name TEXT UNIQUE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_category_id ON items (category_id);")
    
    conn.commit()
    conn.close()

# Run table creation on startup
create_tables()

## **Insert a new item into the database**
def insert_item(item: Item, image: UploadFile = None):
    conn = get_db()
    cursor = conn.cursor()

    image_name = None
    if image:
        image_bytes = image.file.read()
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        image_name = f"{image_hash}.jpg"
        image_path = os.path.join(IMAGE_DIR, image_name)

        if not os.path.exists(image_path):  # Avoid overwriting existing images
            with open(image_path, "wb") as f:
                f.write(image_bytes)

    try:
        cursor.execute("SELECT id FROM categories WHERE name = ?", (item.category,))
        category = cursor.fetchone()

        if category is None:
            cursor.execute("INSERT INTO categories (name) VALUES (?)", (item.category,))
            category_id = cursor.lastrowid
        else:
            category_id = category["id"]

        cursor.execute(
            "INSERT INTO items (name, category_id, image_name) VALUES (?, ?, ?)",
            (item.name, category_id, image_name),
        )

        conn.commit()
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
    finally:
        conn.close()

## **API Endpoint: Add a new item**
@app.post("/items")
def add_item(
    name: str = Form(...),
    category: str = Form(...),
    image: UploadFile = File(None),
):
    insert_item(Item(name=name, category=category), image)
    return {"message": f"Item '{name}' added successfully!"}

## **API Endpoint: Get all items**
@app.get("/items")
def get_items():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT items.id, items.name, categories.name AS category, items.image_name 
        FROM items 
        JOIN categories ON items.category_id = categories.id
        """
    )
    items = cursor.fetchall()
    conn.close()
    return {"items": [dict(item) for item in items]}

## **API Endpoint: Get a single item by ID**
@app.get("/items/{item_id}")
def get_item(item_id: int = Path(..., description="The ID of the item to retrieve")):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT items.id, items.name, categories.name AS category, items.image_name
        FROM items
        JOIN categories ON items.category_id = categories.id
        WHERE items.id = ?
        """,
        (item_id,),
    )
    item = cursor.fetchone()
    conn.close()

    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return dict(item)

## **API Endpoint: Search items by keyword**
@app.get("/search")
def search_items(keyword: str = Query(..., description="Keyword to search for items")):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT items.id, items.name, categories.name AS category, items.image_name 
        FROM items 
        JOIN categories ON items.category_id = categories.id
        WHERE items.name LIKE ? OR categories.name LIKE ?
        """,
        (f"%{keyword}%", f"%{keyword}%"),
    )
    items = cursor.fetchall()
    conn.close()

    return {"items": [dict(item) for item in items]}

## **API Endpoint: Serve images**
@app.get("/images/{image_name}")
async def get_image(image_name: str):
    image_path = os.path.join(IMAGE_DIR, image_name)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)

## **API Endpoint: Root**
@app.get("/")
def read_root():
    return {"message": "Hello, world!"}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
