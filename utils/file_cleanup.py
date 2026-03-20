import os


def delete_file(file_field):

    if not file_field:
        return

    try:
        if os.path.isfile(file_field.path):
            os.remove(file_field.path)
    except Exception:
        pass