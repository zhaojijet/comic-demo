#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import gzip
import base64
import zlib
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Union, Optional
import hashlib

@dataclass
class CompressedFile:
    """Data class for compressed file information"""
    filename: str
    original_size: int
    compressed_size: int
    compression_ratio: str
    method: str
    md5: str
    base64: str

class FileCompressor:
    """File compression and encoding utility class"""
    
    @staticmethod
    def calculate_md5(data: bytes) -> str:
        """Calculate MD5 hash of data"""
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def compress_and_encode(
        file_path: Union[str, Path], 
        method: str = 'gzip'
    ) -> CompressedFile:
        """
        Compresses a file and encodes it in Base64.
        :param file_path: Path to the file.
        :param method: Compression method ('gzip' or 'zlib').
        :return: A CompressedFile object containing the encoded data and metadata.
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'rb') as f:
            original_data = f.read()
        
        original_md5 = hashlib.md5(original_data).hexdigest()
        original_size = len(original_data)
        
        if method == 'gzip':
            compressed_data = gzip.compress(
                original_data, 
            )
        elif method == 'zlib':
            compressed_data = zlib.compress(
                original_data, 
            )
        else:
            raise ValueError(f"Unsupported compression method: {method}")
        
        compressed_size = len(compressed_data)
        
        encoded_data = base64.b64encode(compressed_data).decode('utf-8')
        
        return CompressedFile(
            filename=file_path.name,
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=f"{(1 - compressed_size/original_size)*100:.2f}%",
            method=method,
            md5=original_md5,
            base64=encoded_data
        )
    
    @staticmethod
    def decode_and_decompress(
        encoded_file: CompressedFile, 
        output_path: Optional[Union[str, Path]] = None
    ) -> bytes:

        compressed_data = base64.b64decode(encoded_file.base64)
        
        method = encoded_file.method
        if method == 'gzip':
            original_data = gzip.decompress(compressed_data)
        elif method == 'zlib':
            original_data = zlib.decompress(compressed_data)
        else:
            raise ValueError(f"Unsupported compression method: {method}")
        
        decoded_md5 = hashlib.md5(original_data).hexdigest()
        if decoded_md5 != encoded_file.md5:
            raise ValueError("MD5 checksum verification failed — the file may be corrupted.")
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(original_data)
        
        return original_data
    
    @staticmethod
    def save_encoded_to_json(encoded_file: CompressedFile, json_path: Union[str, Path]):
        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(asdict(encoded_file), f, indent=2, ensure_ascii=False)
    
    @staticmethod
    def load_encoded_from_json(json_path: Union[str, Path]) -> CompressedFile:
        json_path = Path(json_path)
        
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return CompressedFile(**json.load(f))

    @staticmethod
    def decompress_from_string(
        encoded_string: str, 
        output_path: Union[str, Path],
        method: str = 'gzip'
    ) -> bytes:

        compressed_data = base64.b64decode(encoded_string)
        
        if method == 'gzip':
            original_data = gzip.decompress(compressed_data)
        elif method == 'zlib':
            original_data = zlib.decompress(compressed_data)
        else:
            raise ValueError(f"Unsupported compression method: {method}")
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(original_data)
        
        return original_data