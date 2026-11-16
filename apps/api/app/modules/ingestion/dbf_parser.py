import io
import struct
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass
class DbfField:
    name: str
    field_type: str
    length: int
    decimals: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.field_type,
            "length": self.length,
            "decimals": self.decimals,
        }


@dataclass
class DbfTable:
    file_name: str
    table_name: str
    encoding: str
    version: int
    last_update: str | None
    record_count: int
    active_record_count: int
    deleted_record_count: int
    header_length: int
    record_length: int
    language_driver: int
    fields: list[DbfField]
    rows: list[dict[str, Any]]


def _decode_text(raw: bytes, encoding: str) -> str:
    return raw.decode(encoding, errors="replace").strip()


def _parse_number(raw: bytes, decimals: int) -> int | float | None:
    value = raw.decode("ascii", errors="replace").strip()
    if not value or value in {"*", "."}:
        return None
    try:
        if decimals == 0 and "." not in value:
            return int(value)
        return float(value)
    except ValueError:
        return None


def _parse_date(raw: bytes) -> str | None:
    value = raw.decode("ascii", errors="replace").strip()
    if len(value) != 8 or not value.isdigit() or value == "00000000":
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8])).isoformat()
    except ValueError:
        return None


def _parse_logical(raw: bytes) -> bool | None:
    value = raw.decode("ascii", errors="replace").strip().upper()
    if value in {"Y", "T", "1"}:
        return True
    if value in {"N", "F", "0"}:
        return False
    return None


def _parse_value(raw: bytes, field: DbfField, encoding: str) -> Any:
    if field.field_type in {"C", "V"}:
        return _decode_text(raw, encoding)
    if field.field_type in {"N", "F"}:
        return _parse_number(raw, field.decimals)
    if field.field_type == "D":
        return _parse_date(raw)
    if field.field_type == "L":
        return _parse_logical(raw)
    if field.field_type == "I":
        return struct.unpack("<i", raw[:4])[0] if len(raw) >= 4 else None
    if field.field_type == "B":
        return raw.hex()
    if field.field_type == "M":
        return _decode_text(raw, encoding)
    return raw.hex()


def parse_dbf_bytes(data: bytes, file_name: str) -> DbfTable:
    if len(data) < 32:
        raise ValueError(f"{file_name} 不是有效的 DBF 文件")
    version = data[0]
    last_update = None
    if data[1] and data[2] and data[3]:
        last_update = f"{1900 + data[1]:04d}-{data[2]:02d}-{data[3]:02d}"

    record_count = struct.unpack("<I", data[4:8])[0]
    header_length = struct.unpack("<H", data[8:10])[0]
    record_length = struct.unpack("<H", data[10:12])[0]
    language_driver = data[29]

    fields: list[DbfField] = []
    position = 32
    while position < header_length and data[position] != 0x0D:
        descriptor = data[position:position + 32]
        if len(descriptor) < 32:
            break
        name = descriptor[0:11].split(b"\x00", 1)[0].decode("ascii", errors="replace")
        fields.append(
            DbfField(
                name=name,
                field_type=chr(descriptor[11]),
                length=descriptor[16],
                decimals=descriptor[17],
            )
        )
        position += 32

    encoding = "gb18030"
    rows: list[dict[str, Any]] = []
    deleted_count = 0
    for index in range(record_count):
        start = header_length + index * record_length
        record = data[start:start + record_length]
        if len(record) < record_length:
            break
        if record[0:1] == b"*":
            deleted_count += 1
            continue

        offset = 1
        row: dict[str, Any] = {}
        for field in fields:
            raw = record[offset:offset + field.length]
            offset += field.length
            row[field.name] = _parse_value(raw, field, encoding)
        rows.append(row)

    return DbfTable(
        file_name=file_name,
        table_name=Path(file_name).stem.lower(),
        encoding=encoding,
        version=version,
        last_update=last_update,
        record_count=record_count,
        active_record_count=len(rows),
        deleted_record_count=deleted_count,
        header_length=header_length,
        record_length=record_length,
        language_driver=language_driver,
        fields=fields,
        rows=rows,
    )


def parse_dbf_file(path: Path) -> DbfTable:
    return parse_dbf_bytes(path.read_bytes(), path.name)


def iter_dbf_from_zip(zip_bytes: bytes) -> list[DbfTable]:
    tables: list[DbfTable] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        for name in sorted(archive.namelist(), key=str.lower):
            if not name.lower().endswith(".dbf"):
                continue
            tables.append(parse_dbf_bytes(archive.read(name), Path(name).name))
    if not tables:
        raise ValueError("压缩包中没有找到 DBF 文件")
    return tables
