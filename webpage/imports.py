import streamlit as st
import openai
import faiss
import langchain
import pandas as pd
from sqlalchemy import (
    select, create_engine, Table, Column, Integer, String, MetaData,
    ForeignKey, ForeignKeyConstraint, UniqueConstraint, LargeBinary, text
)
from sqlalchemy.orm import Session, sessionmaker

from pdf2image import convert_from_path
import os
import re
import pdfplumber
import fitz  # PyMuPDF
import io

from IPython.display import display, Image
from PIL import Image
from io import BytesIO
from IPython.display import display, Image as IPImage

# ------------------- Database Connection -------------------
# Replace values with your actual database info
username = "postgres"
password = "MPAMS"
host = "localhost"
port = "5432"
database = "MPDB"
# SQLAlchemy connection URL
DATABASE_URL = f"postgresql://{username}:{password}@{host}:{port}/{database}"
# Create engine
engine = create_engine(DATABASE_URL)