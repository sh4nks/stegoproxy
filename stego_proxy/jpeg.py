def append_text(text_to_append, file_path):
    with open(file_path, "ab") as fp:
        fp.write(text_to_append.encode("utf-8"))


def extract_text(file_path):
    # doesn't check the size of the file - be careful when opening
    # really large files!
    with open(file_path, "rb") as fp:
        s = fp.read()
        position = s.rfind(b"\xff\xd9") + 2
        return s[position:]


if __name__ == "__main__":
    print(extract_text("../append_modified.jpg"))
