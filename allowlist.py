from pathlib import Path


class AllowList:
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.id_list = []
        if not self.file_exists(self.filename):
            with open(self.filename, mode="w") as f:
                pass
        else:
            self.load()

    def file_exists(self, filename: str) -> bool:
        return Path(filename).exists()

    def add_user(self, id: str) -> None:
        if id not in self.id_list:
            self.id_list.append(id)

    def remove_user(self, id: str) -> None:
        if id in self.id_list:
            self.id_list.pop(self.id_list.index(id))

    def user_exists(self, id: str) -> bool:
        return True if id in self.id_list else False

    def save(self) -> None:
        with open(self.filename, mode="w") as f:
            for id in self.id_list:
                f.write(id + "\n")

    def load(self) -> None:
        if self.file_exists(self.filename):
            self.id_list.clear()
            with open(self.filename, mode="r") as f:
                lines = f.readlines()
            for line in lines:
                self.id_list.append(str(line).strip().replace("\n", ""))
