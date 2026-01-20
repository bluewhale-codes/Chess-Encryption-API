from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError

# import from utils
from utils import allowed_file , get_safe_filename

from fastapi.middleware.cors import CORSMiddleware

import os
import logging
from encode import encode
from decode import decode

from uuid import uuid4



# -------------------------------------
# FastAPI App
# -------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React app URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

# Maximum upload size: 5 MB
MAX_FILE_SIZE_MB = 1
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def make_error(code: str, message: str) -> dict:
    """
    Standardize error structure for frontend consumption.
    """
    return {"code": code, "message": message}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Ensure all HTTPException responses have a consistent JSON shape.
    """
    detail = exc.detail

    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        error_payload = detail
    else:
        error_payload = make_error("HTTP_ERROR", str(detail))

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error_payload},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Convert FastAPI validation errors (e.g., missing form fields) into
    a consistent shape.
    """
    logger.warning("Request validation error: %s", exc.errors())

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request payload",
                "details": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for any unhandled exception.
    """
    logger.exception("Unhandled server error")

    return JSONResponse(
        status_code=500,
        content={
            "error": make_error(
                "INTERNAL_SERVER_ERROR",
                "An unexpected error occurred. Please try again later.",
            )
        },
    )


@app.post("/encode")
async def handle_encode(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form(...),
    self_destruct_timer: int | None = Form(None),

    # PGN headers
    pgn_event: str | None = Form(None),
    pgn_site: str | None = Form(None),
    pgn_date: str | None = Form(None),
    pgn_round: str | None = Form(None),
    pgn_white: str | None = Form(None),
    pgn_black: str | None = Form(None),
    pgn_whiteelo: str | None = Form(None),
    pgn_blackelo: str | None = Form(None),
    pgn_result: str | None = Form(None),
    pgn_eco: str | None = Form(None),
):
    logger.debug("Starting encode request")

    try:
        # Basic presence validation
        if not file or not file.filename:
            raise HTTPException(
                status_code=400,
                detail=make_error("NO_FILE", "No file uploaded."),
            )

        # Normalize and validate file_type
        file_type_normalized = (file_type or "").strip().lower()
        if file_type_normalized not in ["text", "image"]:
            raise HTTPException(
                status_code=400,
                detail=make_error("INVALID_FILE_TYPE", "Invalid file type."),
            )

        # Validate self_destruct_timer if provided
        if self_destruct_timer is not None and self_destruct_timer <= 0:
            raise HTTPException(
                status_code=400,
                detail=make_error(
                    "INVALID_TIMER", "self_destruct_timer must be a positive integer."
                ),
            )

        # Validate extension
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=make_error("DISALLOWED_FILE_EXT", "File type not allowed."),
            )

        safe_filename = get_safe_filename(file.filename)
        unique_suffix = uuid4().hex
        input_path = os.path.join(UPLOAD_FOLDER, f"{unique_suffix}_{safe_filename}")
        output_path = os.path.join(
            OUTPUT_FOLDER, f"{unique_suffix}_encoded_output.pgn"
        )

        # Read and enforce max size
        data = await file.read()
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=make_error(
                    "FILE_TOO_LARGE",
                    f"File is too large. Maximum allowed size is {MAX_FILE_SIZE_MB} MB.",
                ),
            )

        # Save uploaded file
        try:
            with open(input_path, "wb") as buffer:
                buffer.write(data)
        except OSError:
            logger.exception("Failed to write uploaded file to disk")
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "FILE_WRITE_ERROR",
                    "Failed to save uploaded file. Please try again later.",
                ),
            )

        # Build custom PGN headers
        custom_headers = {
            "Event": pgn_event,
            "Site": pgn_site,
            "Date": pgn_date,
            "Round": pgn_round,
            "White": pgn_white,
            "Black": pgn_black,
            "WhiteElo": pgn_whiteelo,
            "BlackElo": pgn_blackelo,
            "Result": pgn_result,
            "ECO": pgn_eco,
        }

        # Remove None values
        custom_headers = {k: v for k, v in custom_headers.items() if v}

        # Perform encoding
        try:
            encode(
                input_path,
                output_path,
                self_destruct_timer,
                custom_headers if custom_headers else None,
            )
        except Exception:
            logger.exception("Encoding failed")
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "ENCODING_FAILED",
                    "Failed to encode file. Please verify the input and try again.",
                ),
            )

        if not os.path.exists(output_path):
            logger.error("Output file was not created: %s", output_path)
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "OUTPUT_NOT_CREATED",
                    "Output file was not created. Please try again.",
                ),
            )

        return FileResponse(
            output_path,
            media_type="application/octet-stream",
            filename="encoded_output.pgn",
        )

    except HTTPException:
        # Let HTTPExceptions bubble up to the global handler
        raise
    except Exception:
        logger.exception("Unexpected error in /encode")
        raise HTTPException(
            status_code=500,
            detail=make_error(
                "UNEXPECTED_ERROR", "An unexpected error occurred during encoding."
            ),
        )


@app.post("/decode")
async def handle_decode(
    request: Request,
    file: UploadFile = File(...),
    file_type: str = Form(...)
):
    try:
        logger.debug("Starting decode request")

        # ✅ Validate filename
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail=make_error("NO_FILE", "No file uploaded."),
            )

        logger.debug(f"Received file: {file.filename}")
        logger.debug(f"File type: {file_type}")

        # ✅ Validate file_type
        file_type_normalized = (file_type or "").strip().lower()
        if file_type_normalized not in ["text", "image"]:
            raise HTTPException(
                status_code=400,
                detail=make_error("INVALID_FILE_TYPE", "Invalid file type."),
            )

        # ✅ Validate extension
        if not allowed_file(file.filename):
            raise HTTPException(
                status_code=400,
                detail=make_error("DISALLOWED_FILE_EXT", "File type not allowed."),
            )

        safe_filename = get_safe_filename(file.filename)
        unique_suffix = uuid4().hex
        input_path = os.path.join(UPLOAD_FOLDER, f"{unique_suffix}_{safe_filename}")

        # ✅ Save uploaded file with size limit
        data = await file.read()
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=make_error(
                    "FILE_TOO_LARGE",
                    f"File is too large. Maximum allowed size is {MAX_FILE_SIZE_MB} MB.",
                ),
            )

        try:
            with open(input_path, "wb") as buffer:
                buffer.write(data)
        except OSError:
            logger.exception("Failed to write uploaded file to disk (decode)")
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "FILE_WRITE_ERROR",
                    "Failed to save uploaded file. Please try again later.",
                ),
            )

        logger.debug(f"Saved file to: {input_path}")

        output_extension = "txt" if file_type_normalized == "text" else "png"
        output_path = os.path.join(
            OUTPUT_FOLDER, f"decoded_output.{output_extension}"
        )

        logger.debug(f"Output path: {output_path}")

        # ✅ Decode
        try:
            decode(input_path, output_path)
            logger.debug("Decoding completed")
        except Exception:
            logger.exception("Decoding failed")
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "DECODING_FAILED",
                    "Failed to decode file. Please ensure the file is valid.",
                ),
            )

        # ✅ Ensure output exists
        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=500,
                detail=make_error(
                    "OUTPUT_NOT_CREATED",
                    "Output file was not created. Please try again.",
                ),
            )

        logger.debug("Sending decoded file")

        return FileResponse(
            output_path,
            media_type="application/octet-stream",
            filename=f"decoded_output.{output_extension}"
        )

    except HTTPException:
        # Let HTTPExceptions bubble up to the global handler
        raise
    except Exception:
        logger.exception("Unexpected error in /decode")
        raise HTTPException(
            status_code=500,
            detail=make_error(
                "UNEXPECTED_ERROR", "An unexpected error occurred during decoding."
            ),
        )

