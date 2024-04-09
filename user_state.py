# this is used to keep track of what users are doing.

from enum import Enum
import hashlib
import json
import logging
from typing import Optional


class UserStates:
    class MessageTypes(Enum):
        COMMAND = "Command"
        PROMPT = "Prompt"
        IMAGE = "Image"

    class LLMTypes(Enum):
        GPT = "GPT"
        GEMINI = "Gemini"
        BOTH = "GPT & Gemini"

    def __init__(self, logger: logging.Logger) -> None:
        self.users = {}
        self.logger = logger.getChild("user_state")

    def usercheck(func):
        def usercheck_wrapper(self, username: int | str, *args, **kwargs):
            username = str(username)
            if not self.user_state_exists(username):
                self.add_user(username)
            return func(self, username, *args, **kwargs)

        return usercheck_wrapper

    def save_data_change(func):
        def enum_serailizer(obj):
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(f"Type {obj.__class__.__name__} not serializable")

        def save_data_change_wrapper(self, *args, **kwargs):
            hash_before = hashlib.sha256(
                json.dumps(self.users, sort_keys=True, default=enum_serailizer).encode()
            ).hexdigest()
            res = func(self, *args, **kwargs)
            # detect if we should save
            after_hash = hashlib.sha256(
                json.dumps(self.users, sort_keys=True, default=enum_serailizer).encode()
            ).hexdigest()
            if hash_before != after_hash:
                self.logger.info("State of users has changed: Saving")
                # Save user states.
            return res

        return save_data_change_wrapper

    def user_state_exists(self, username: int | str) -> bool:
        username = str(username)
        if username in self.users.keys():
            return True
        return False

    def remove_user_state(self, username: int | str) -> None:
        self.users.pop(username, "")

    def add_user(self, username: int | str) -> None:
        username = str(username)
        if not self.user_state_exists(username):
            self.users[username] = self.create_user_state(username)

    @usercheck
    def update_prompt(
        self,
        username: int | str,
        prompt_to: LLMTypes,
        prompt: Optional[str] = None,
        prompt_result: Optional[str] = None,
        do_not_increase=False,
    ):
        self.users[username]["last_message_type"] = self.MessageTypes.PROMPT
        if not do_not_increase:
            if prompt_to == self.LLMTypes.GPT:
                self.users[username]["chatgpt_prompts"] += 1
            elif prompt_to == self.LLMTypes.GEMINI:
                self.users[username]["gemini_prompts"] += 1
            elif prompt_to == self.LLMTypes.BOTH:
                self.users[username]["chatgpt_prompts"] += 1
                self.users[username]["gemini_prompts"] += 1
        self.users[username]["last_prompt_state"]["prompt"] = (
            self.users[username]["last_prompt_state"]["prompt"]
            if prompt is None
            else prompt
        )
        self.users[username]["last_prompt_state"]["prompt_to"] = prompt_to
        self.users[username]["last_prompt_state"]["prompt_result"] = (
            self.users[username]["last_prompt_state"]["prompt_result"]
            if prompt_result is None
            else prompt_result
        )

    @usercheck
    def update_pic(
        self,
        username: int | str,
        prompt: Optional[str] = None,
        prompt_result: Optional[str] = None,
    ):
        # anything that is not None should be updated.
        self.users[username]["pics"] += 1
        self.users[username]["last_message_type"] = self.MessageTypes.IMAGE
        self.users[username]["last_pic_state"]["prompt"] = (
            self.users[username]["last_pic_state"]["prompt"]
            if prompt is None
            else prompt
        )
        self.users[username]["last_pic_state"]["file_result"] = (
            self.users[username]["last_pic_state"]["file_result"]
            if prompt_result is None
            else prompt_result
        )

    @save_data_change
    @usercheck
    def update_command(
        self,
        username: int | str,
        prompt: Optional[str] = None,
        prompt_result: Optional[str] = None,
    ):
        # anything that is not None should be updated.  Note that prompt = command, ect...
        self.users[username]["last_command_state"]["command"] = (
            self.users[username]["last_command_state"]["command"]
            if prompt is None
            else prompt
        )
        self.users[username]["last_command_state"]["command_result"] = (
            self.users[username]["last_command_state"]["command_result"]
            if prompt_result is None
            else prompt_result
        )
        self.users[username]["commands"] += 1
        self.users[username]["last_message_type"] = self.MessageTypes.COMMAND

    @usercheck
    def update_user_response_required(
        self,
        username: int | str,
        response_required: bool,
        state_memory: Optional[str] = None,
        command: Optional[str] = None,
    ) -> None:
        self.users[username]["awaiting_response"] = response_required
        self.users[username]["last_command_state"]["state_memory"] = (
            self.users[username]["last_command_state"]["state_memory"]
            if state_memory is None
            else state_memory
        )
        self.users[username]["last_command_state"]["command"] = (
            self.users[username]["last_command_state"]["command"]
            if command is None
            else command
        )
        self.users[username]["last_message_type"] = self.MessageTypes.COMMAND
        self.users[username]["commands"] += 1

    @usercheck
    def clear_user_response_required(self, username: int | str) -> None:
        self.users[username]["awaiting_response"] = False
        self.users[username]["last_command_state"]["state_memory"] = ""
        self.users[username]["last_command_state"]["command"] = ""

    def create_user_state(self, username: str) -> dict:
        out_dict = {
            "id": username,
            "pics": 0,
            "chatgpt_prompts": 0,
            "gemini_prompts": 0,
            "commands": 0,
            "last_message_type": "",
            "last_prompt_state": {
                "prompt": "",
                "prompt_to": "",
                "prompt_result": "",
            },
            "last_pic_state": {
                "prompt": "",
                "file_result": "",
            },
            "last_command_state": {
                "command": "",
                "command_result": "",
                "state_memory": "",
            },
            "awaiting_response": False,
        }
        return out_dict

    @usercheck
    def how_many_pics(self, username: str) -> int:
        return self.users[username]["pics"]

    @usercheck
    def how_many_chatgpt_prompts(self, username: str) -> int:
        return self.users[username]["chatgpt_prompts"]

    @usercheck
    def how_many_gemini_prompts(self, username: str) -> int:
        return self.users[username]["gemini_prompts"]

    @usercheck
    def how_many_commands(self, username: str) -> int:
        return self.users[username]["commands"]

    @usercheck
    def get_last_prompt(self, username: str) -> dict:
        return self.users[username]["last_prompt_state"]

    @usercheck
    def get_last_pic(self, username: str) -> dict:
        return self.users[username]["last_pic_state"]

    @usercheck
    def get_last_command(self, username: str) -> dict:
        return self.users[username]["last_command_state"]

    @usercheck
    def get_user_state(self, username: str) -> dict:
        return self.users[username]

    @usercheck
    def get_user_last_action(self, username: str) -> str:
        return self.users[username]["last_message_type"]

    def total_users(self) -> int:
        return len(self.users)

    def save_users(self):
        # TODO : This should save to file or db.
        pass

    def load_users(self):
        # TODO : This should load from file or db.
        pass
