import os
from werkzeug.utils import secure_filename
ALLOWED_EXTENSIONS = {'txt', 'png', 'jpg', 'jpeg', 'pgn'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_safe_filename(filename):
    filename = os.path.basename(filename)
    return secure_filename(filename)