import asyncio
from enum import Enum
import json
import re
import subprocess
import requests
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    filters,
    MessageHandler,
)
from telegram import (
    InputMediaPhoto,
    Update,
    constants,
)
import logging
import random
import os
import time
import allowlist
import string
from app_config import BotConfiguration
from user_state import UserStates
from gpt import LLM_ACCESS


# Name of your systemctl telegram service
TELEGRAM_BOT_SERVICE_NAME = "tgram.service"


# Logger config
LOGGER_NAME = "tgram"
LOGGER_FILE_NAME = "tgram_log.txt"
logger = logging.getLogger(LOGGER_NAME)
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logging_file_handler = logging.FileHandler(LOGGER_FILE_NAME)
logging_file_handler.setLevel(logging.INFO)
logging_file_handler.setFormatter(formatter)
logger.addHandler(logging_file_handler)

# Load config
# TODO : Make this the global configurationer
APP_CONFIG = BotConfiguration("keys.txt", logger)

# LLM class
LLM = LLM_ACCESS(APP_CONFIG, logger)

# Create the allowlist
allow_list = allowlist.AllowList(APP_CONFIG.ALLOW_LIST_FILENAME)

# User states
users = UserStates(logger)


class HelpText:
    def __init__(self) -> None:
        self.commands_dict = {
            "/start": "This list plus a welcome message",
            "long/start": "This list plus a welcome message",
            "/list": "This list",
            "long/list": "This list",
            "/c": "send to chatGPT",
            "long/c": "send to ChatGPT all text after this message.  After that, a response will be returned.  This can take a few seconds to generate.  This uses ChatGPT-4 bot.  Temperature can be set with `t:h/m/l` for high, mid, low.  Lower is less creative (default is m).",
            "/g": "send to Google Gemini",
            "long/g": "Send to Google Gemini all text after this message.  After that, a response will be returned.  This can take a few seconds to generate.  This uses Google Gemini.  WARNING ** Content filters are set low **",
            "/cross": "Cross check Gemini against ChatGPT",
            "long/cross": "Cross check a message that is first checked against gemini then against ChatGPT.",
            "/p": "create me a picture (1024x1024 default)",
            "long/p": "create a picture from a text description.  All text included will create a picture for you.  This is a picture in 1024x1024 format. Other valid arguments are `size:h` and `size:v` for horizontal or verticle.  Also quality can be Standard (default) or HD by `q:hd`.",
            "/aboutme": "Tell us things about you",
            "long/aboutme": "Tells things about your telegram account, and if you have a subject stored.",
            "/help": "<i>command without slash</i> (ex: <code>/help aboutme</code>)",
            "long/help": "Well, if you can type <code>/help help</code> then you can probably figure the rest out 🤣",
            "/feedback": "Provide feedback on the bot.",
            "long/feedback": "Provide feedback to the developer about this bot and how it is working, feature improvements or something else?",
            "/q": "random quote",
            "long/q": "random quote",
            "/listmyimages": "Lists all your images you have created under your account and this bot (if they exist still)",
            "long/listmyimages": "Usage <code>/listmyimages</code> will list all the images you have created with this account if they exist.",
            "/getmyimage": "Get the image by filename",
            "long/getmyimage": "Get the image by filename as listed in the /listmyimages command.  example <code>/getmyimage myimage123456.png</code>",
            "/getallmyimages": "Get all of the images I have saved",
            "long/getallmyimages": "Get all the images I have and send them to me all at once.  They will be in groups of ten at a time.",
        }

    def short_help_all_to_string(self):
        outstr = ""
        for key in self.commands_dict:
            if not "long" in key:
                outstr = outstr + f"{key} -- {self.commands_dict[key]}\n"
        return outstr

    def long_help_by_id(self, id: str):
        outstr = ""
        for key in self.commands_dict:
            if "long" in key and id.lower().strip() in key.split("/")[1]:
                if len(id.lower().strip()) == len(key[key.find("/") + 1:]):
                    outstr = f"{id.strip().lower()} -- {self.commands_dict[key]}\n"
                    return outstr


help_commands = HelpText()  # to use the help system.


# Decorator to determine admin yes/no
def is_admin(func):
    """
    The `is_admin` function is a decorator that checks if the user sending a command is an admin based
    on their user ID before allowing the execution of the decorated function.

    :param func: The `func` parameter in the `is_admin` function is a function that is being wrapped by
    the `is_admin_wrapper` function. This function is expected to handle certain actions or commands
    related to admin privileges. The `is_admin_wrapper` function acts as a decorator that checks if the
    user invoking
    :return: The `is_admin_wrapper` function is being returned.
    """

    async def is_admin_wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user = update.message.from_user
        if str(user.id) == str(APP_CONFIG.ADMIN):
            return await func(update, context, *args, **kwargs)
        else:
            logger.info(
                f"User {user.id} : {user.full_name} is unauthorized to use admin commands."
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Command is not authorized for {user.id} : {user.full_name}",
                parse_mode=constants.ParseMode.HTML,
            )

    return is_admin_wrapper


def check_user_state(func):
    """
    The `check_user_state` function is a Python decorator that ensures a user exists before executing a
    given function.

    :param func: The `func` parameter in the `check_user_state` function is a function that takes
    `update`, `context`, and additional arguments as input and returns an asynchronous result
    :return: The `check_user_state` function is returning a new asynchronous function
    `user_exists_wrapper` that wraps around the original function passed to it as an argument. This
    wrapper function first checks if the user exists in the global `users` set and adds the user if not
    already present, before calling the original function with the provided arguments.
    """

    async def user_exists_wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        global users
        user = update.message.from_user
        users.add_user(user.id)
        return await func(update, context, *args, **kwargs)

    return user_exists_wrapper


def create_random_filename(size: int) -> str:
    if size > 0:
        return "".join(random.choices(string.digits + string.ascii_lowercase, k=size))
    else:
        return ""


def format_data_into_size(number: str) -> list:
    """
    The function `format_data_into_size` takes a number as a string input and returns a list containing
    the long and short format of the data size based on the number of commas in the input.

    :param number: The function `format_data_into_size` takes a string input `number` and converts it
    into a list containing the long and short format of the data size based on the number of commas
    present in the input string
    :type number: str
    :return: The function `format_data_into_size` is returning a list containing the long and short
    format of the data size based on the number of commas in the input string `number`.
    """
    data_long = {
        "0": "Bytes",
        "1": "KiloBytes",
        "2": "MegaBytes",
        "3": "GigaBytes",
        "4": "TeraBytes",
    }
    data_short = {
        "0": "B",
        "1": "KB",
        "2": "MB",
        "3": "GB",
        "4": "TB",
    }
    return [data_long[str(number.count(","))], data_short[str(number.count(","))]]


def format_data_into_str(number: int) -> list:
    """
    The function `format_data_into_str` takes an integer, formats it with commas, calculates the number
    of commas, and returns a list with the formatted number and its size in a shorthand format.

    :param number: The function `format_data_into_str` takes an integer `number` as input and formats it
    into a list of two strings. The first string in the list represents the number in a shortened format
    with the appropriate size indicator, and the second string represents the number in a similar format
    but with a different
    :type number: int
    :return: The function `format_data_into_str` returns a list containing two formatted strings. The
    first string is the input number formatted with commas and a size indicator, while the second string
    is a shorthand version of the input number with a decimal point and a size indicator.
    """
    num_as_str = "{:,}".format(number)
    commas = num_as_str.count(",")
    if commas == 0:
        return [
            num_as_str + " " + format_data_into_size(num_as_str)[0],
            num_as_str + " " + format_data_into_size(num_as_str)[1],
        ]
    shorthand_num = num_as_str.split(",")[0] + "." + num_as_str.split(",")[1][0:2]
    type_list = format_data_into_size(num_as_str)
    return [shorthand_num + " " + type_list[0], shorthand_num + " " + type_list[1]]


async def get_memory_usage():
    """
    This Python async function reads memory information from /proc/meminfo and calculates total, used,
    and free memory before returning a formatted string with the results.
    :return: The `get_memory_usage` function is returning a formatted string containing information
    about memory usage. The string includes the total memory, used memory, and free memory. The values
    are obtained from reading and parsing the `/proc/meminfo` file in the Linux system.
    """
    with open("/proc/meminfo", "r") as meminfo_file:
        meminfo = meminfo_file.read()
        memtotal = (
            int(
                next(
                    filter(lambda x: x.startswith("MemTotal"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        memfree = (
            int(
                next(
                    filter(lambda x: x.startswith("MemFree"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        memavailable = (
            int(
                next(
                    filter(lambda x: x.startswith("MemAvailable"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        buffers = (
            int(
                next(
                    filter(lambda x: x.startswith("Buffers"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        cached = (
            int(
                next(
                    filter(lambda x: x.startswith("Cached"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        sreclaimable = (
            int(
                next(
                    filter(lambda x: x.startswith("SReclaimable"), meminfo.splitlines())
                ).split()[1]
            )
            * 1024
        )
        memused = memtotal - (memfree + buffers + cached + sreclaimable)
        return f"total: {format_data_into_str(memtotal)[1]} | used: {format_data_into_str(memused)[1]} | free: {format_data_into_str(memavailable)[1]}"


def get_cpu_usage_raw():
    with open("/proc/stat", "r") as f:
        lines = f.readlines()
    cpu_usages = []
    for line in lines:
        if line.startswith("cpu"):
            fields = [float(column) for column in line.strip().split()[1:]]
            # idle time is the fourth column in /proc/stat
            idle_time = fields[3]
            total_time = sum(fields)
            cpu_usages.append((total_time, idle_time))
    return cpu_usages


async def get_cpu_usage():
    prev_usage = get_cpu_usage_raw()
    time.sleep(1)
    curr_usage = get_cpu_usage_raw()

    cpu_pct = []
    for prev, cur in zip(prev_usage, curr_usage):
        prev_total, prev_idle = prev
        cur_total, cur_idle = cur

        total_diff = cur_total - prev_total
        idle_diff = cur_idle - prev_idle

        cpu_pcts = 100 * (1 - (idle_diff / total_diff))
        cpu_pct.append(cpu_pcts)

    out_str = ""
    for i, cpu_p in enumerate(cpu_pct):
        if i == 0:
            out_str += f"ALL : {cpu_p:.2f}% | "
        else:
            out_str += f"CPU{i-1}: {cpu_p:.2f}% | "
    return out_str[:-2]


async def get_disk_usage():
    # Get disk space usage
    statvfs = os.statvfs("/")
    blksize = statvfs.f_frsize
    total_blocks = statvfs.f_blocks
    free_blocks = statvfs.f_bfree
    avail_blocks = statvfs.f_bavail
    used_blocks = total_blocks - free_blocks
    total_final = total_blocks * blksize
    used_final = used_blocks * blksize
    avail_final = avail_blocks * blksize
    return f"total: {format_data_into_str(total_final)[1]} | used: {format_data_into_str(used_final)[1]} | free: {format_data_into_str(avail_final)[1]}"


@is_admin
@check_user_state
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Sending list of allowed users")
    out_txt = "Allowed Users:\n\n"
    for id in allow_list.id_list:
        out_txt += id + "\n"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_txt,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Adding user to list?")
    words_joined = " ".join(context.args)
    words_joined = words_joined.strip()
    out_msg = ""
    if not " " in words_joined and len(words_joined) > 0:
        allow_list.add_user(words_joined)
        allow_list.save()
        out_msg = f"Added {words_joined} to the allowed user list."
        logger.info(f"Added user '{words_joined}'")
    else:
        out_msg = f"Could not add {words_joined} to the allowed user list."
        logger.info(f"Cannot add user '{words_joined}'")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Removing user from the allowed list?")
    words_joined = " ".join(context.args)
    words_joined = words_joined.strip()
    out_msg = ""
    if words_joined not in allow_list.id_list:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"{words_joined} is not in the allowed list.",
            parse_mode=constants.ParseMode.HTML,
        )
        return
    if not " " in words_joined and len(words_joined) > 0:
        allow_list.remove_user(words_joined)
        allow_list.save()
        out_msg = f"Removed {words_joined} from the allowed user list."
        logger.info(f"Removed '{words_joined}'")
    else:
        logger.info(f"Cannot remove user '{words_joined}'")
        out_msg = f"Could not remove {words_joined} from the allowed user list."
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def toggle_allow_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(
        f"Admin : Changing the allow list usage from {APP_CONFIG.USE_ALLOW_LIST} to {not APP_CONFIG.USE_ALLOW_LIST}"
    )
    out_msg = f"Changing Allow-list usage from {APP_CONFIG.USE_ALLOW_LIST} to {not APP_CONFIG.USE_ALLOW_LIST} \n"
    APP_CONFIG.USE_ALLOW_LIST = not APP_CONFIG.USE_ALLOW_LIST
    out_msg += f"New status: {APP_CONFIG.USE_ALLOW_LIST}\n"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    help_msg = f" 📢 Welcome to the customized GPT experiment, {user.username} 📢.  I can do a few things, here's a list:\n\n "
    help_msg = (
        help_msg + help_commands.short_help_all_to_string() + "\n\n... More to come! 😎"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def quote_picker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    try:
        with open(APP_CONFIG.QUOTE_FILE, "r") as f:
            quote_list = f.readlines()
        quote_list = [x.strip("\n") for x in quote_list]
        quote = "<i>" + random.choice(quote_list) + "</i>"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=quote,
            parse_mode=constants.ParseMode.HTML,
        )
    except Exception as e:
        quote = "<i>Quotes are not set up correctly.  The admin of this bot has been notified.</i>"
        logger.info(f"(QUOTE) file '{APP_CONFIG.QUOTE_FILE}' issue: {e}")
        await send_to_admin(
            f"QUOTE_COMMAND -- user: {user.name}:{user.id} got error :{e}", context
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=quote,
            parse_mode=constants.ParseMode.HTML,
        )


@check_user_state
async def about_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    usr = {}
    usr["firstname"] = user.first_name
    if user.last_name == None:
        usr["lastname"] = " <i>not listed</i> 😠"
    else:
        usr["lastname"] = user.last_name
    if user.is_bot:
        usr["bot"] = " 🤖 Yes, you are a bot."
    else:
        usr["bot"] = " 🙂 No, you are not a bot."
    usr["lang"] = user.language_code
    usr["username"] = user.username
    usr["id"] = user.id
    usr["link"] = user.link
    out_str = f"First Name: {usr['firstname']}\nLast Name: {usr['lastname']}\nAre you a bot? {usr['bot']}\nDefault Language: {usr['lang']}\nUsername: {usr['username']}\nUser ID: {usr['id']}\nLink: {usr['link']}\n\n"
    if str(user.id) == APP_CONFIG.ADMIN:
        out_str += "\n👑 You are the admin 🔑\nRemember you can type /admin "
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_str,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def memory_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    mem = await get_memory_usage()
    logger.info(f"Sending memory status: {mem}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=mem, parse_mode=constants.ParseMode.HTML
    )


@is_admin
@check_user_state
async def disk_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    disk = await get_disk_usage()
    logger.info(f"Sending disk status: {disk}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=disk, parse_mode=constants.ParseMode.HTML
    )


@is_admin
@check_user_state
async def cpu_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cpu = await get_cpu_usage()
    logger.info(f"Sending cpu status: {cpu}")
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=cpu, parse_mode=constants.ParseMode.HTML
    )


@is_admin
@check_user_state
async def get_system_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    cpu = await get_cpu_usage()
    cpu = cpu.split("|")[0].split(":")[1].strip()
    mem = await get_memory_usage()
    mem = mem.split("|")[2]
    disk = await get_disk_usage()
    disk = disk.split("|")[2]
    user_count = users.total_users()
    outstr = f"<b>[System Stats]</b>\n-----------------------\n CPU 🖥️   <code> {cpu}</code>\nMEM 🤔 <code>{mem}</code>\n DISK 💾 <code>{disk}</code>\n Allow Enabled : <code>{APP_CONFIG.USE_ALLOW_LIST}</code>\n Users Allow-listed: <code>{len(allow_list.id_list)}</code>  /listusers\n Users Active: <code>{user_count}</code> /getuserlist"
    logger.info(f"Sending system status.")
    users.update_command(user.id, "/sys", outstr)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=outstr,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def list_all_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Listing all models for Admin.")
    try:
        gemini_models = LLM.get_gemini_models()
        openai_models = LLM.get_openai_models()
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        await send_to_admin(
            f"LISTMODELS_COMMAND -- got error :{e}", context
        )
        return
    out_str = f"<b>Gemini</b> has {len(gemini_models)} models which are : \n {', '.join(gemini_models)}"
    out_str += f"\n\n<b>OpenAI</b> has {len(openai_models)} models which are : \n {', '.join(openai_models)}"
    out_str += f"\n\n CURRENT MODELS\nOpenAI Model : <code>{APP_CONFIG.CHAT_GPT_MODEL}</code>\nGemini Model : <code>{APP_CONFIG.GEMINI_MODEL}</code>"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_str,
        parse_mode=constants.ParseMode.HTML,
    )


async def send_to_admin(message: str, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Sending message to admin.")
    await context.bot.send_message(
        chat_id=APP_CONFIG.ADMIN, text=message, parse_mode=constants.ParseMode.HTML
    )


@check_user_state
async def list_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_msg = help_commands.short_help_all_to_string()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def get_log_lines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    line_count = 6
    words_joined = " ".join(context.args) + " "
    start_location = words_joined.find("L:")
    if start_location > -1:
        # change line count
        end_location = words_joined[start_location:].find(" ")
        potential_new_num_with_arg = words_joined[start_location:end_location]
        potential_new_num = potential_new_num_with_arg.split(":")[1].strip()
        if potential_new_num.isnumeric():
            line_count = int(potential_new_num)
    with open(LOGGER_FILE_NAME, "r") as f:
        lines = f.readlines()
    outStr = f"[ LAST {line_count} LINES FROM LOG ]\n------------------------------\n"
    for c, line in enumerate(lines[-line_count:], start=1):
        outStr += f"[{c}.] - {line}\n"
    logger.info(f"Admin asked for {line_count} lines of log.")
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=outStr,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def admin_help_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Sending help commands to admin.")
    msg = """
        <b>System Commands</b>
        /mem -- Free memory detail
        /cpu -- Used CPU detail
        /disk -- Used disk detail
        /sys -- brief of the above
        /log -- get last 6 log lines (use L:# to change lines and put a space after the number)
        /restart -- restarts  the telegram bot with a delay
        /listmodels -- lists all models for all LLM's that are in use.
        /model [chatgpt|gemini] [modelname] -- change the model being used.  Empty command will return the models in use."
        /savemodels -- saves the models in use so they are persistent through reload/reboot.
        /searchmodels <txt> -- search models for text i.e. /searchmodels o3

        
        <b>Working with saved items</b>
        /listallimages -- lists ALL the images we have saved on the disk.
        /getallimages -- Get ALL the images saved.
        /getimage (imagefilename) -- sends you the image from disk.

        <b>Allow List Commands</b>
        /listusers -- list the ID of the allowed users
        /adduser -- Add a user by ID to the allowed list
        /removeuser -- Remove a user by ID from the allowed list
        /toggleallow -- Toggles the use of the global allow list
        
        <b>Working with Users and their states</b>
        /getmyuserstate -- get a JSON of the users' state.  Built for anyone to use, but shows only on admin help.
        /getuserstate (userid) -- same as above but get another users' state.  Only for admin.
        /getuserlist -- gets a list of all user ID's stored currently.
    
        <b>Misc Commands</b>
        /html -- show html useages
        /pr -- who's the princess?
        /frog -- what frogs?
    
        """
    await send_to_admin(msg, context)


@is_admin
@check_user_state
async def get_list_of_user_states(update: Update, context: ContextTypes.DEFAULT_TYPE):
    out_msg = ""
    for user in users.users.keys():
        out_msg += f"{user}\n"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out_msg,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
@check_user_state
async def list_all_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Listing all images for Admin")
    out_msg = list_images_raw()
    msgs = [out_msg[i: i + 4094] for i in range(0, len(out_msg), 4096)]
    for text_out in msgs:
        await update.message.reply_text(text=text_out)
    return


@check_user_state
async def list_my_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Listing all images for user {user.id} : {user.full_name}")
    out_msg = list_images_by_user(user.id)
    msgs = [out_msg[i: i + 4094] for i in range(0, len(out_msg), 4096)]
    for text_out in msgs:
        await update.message.reply_text(text=text_out)
    return


@check_user_state
async def get_my_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    words_joined = str(" ".join(context.args)).strip().lower()
    logger.info(f"User {user.id} : {user.name} requesting image : {words_joined}")
    msg_out = f"Filename is invalid {words_joined}"
    if words_joined.count("_") > 0:
        if words_joined.split("_")[0] == str(user.id):
            filename_request = os.path.join(os.getcwd(), "images", words_joined)
            if os.path.isfile(filename_request):
                await context.bot.sendPhoto(
                    chat_id=update.effective_chat.id,
                    photo=filename_request,
                    filename=filename_request.split("_")[1],
                    reply_to_message_id=update.message.message_id,
                )
                return
            else:
                msg_out = f"That image doesn't exist '{words_joined}'"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
        reply_to_message_id=update.message.message_id,
    )
    logger.info(f"User {user.id} : {user.name} failed to get image : {words_joined}")


@check_user_state
async def get_all_my_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    list_of_files = list_images_by_user_as_list(user.id)
    logger.info(
        f"Request for all images from {user.id} : {user.full_name} -- {len(list_of_files)} files"
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Sending you {len(list_of_files)} images, in groups of 10.  I'll let you know when I'm done.",
    )

    # Function to split the list of files into chunks of 10
    def split_list_in_chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i: i + n]

    # Splitting the list of files into chunks of 10
    chunks_of_files = list(split_list_in_chunks(list_of_files, 10))
    # Iterating over each chunk and sending them as separate media groups
    for index, chunk in enumerate(chunks_of_files):
        media_group = []
        try:
            for file_path in chunk:
                with open(file_path, "rb") as f:
                    media_group.append(InputMediaPhoto(f))
                    # Note: We're directly passing the file object to InputMediaPhoto
            if media_group:
                await context.bot.send_media_group(
                    chat_id=update.effective_chat.id, media=media_group
                )
                await asyncio.sleep(0.5)
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="No images found."
                )
                return
        except Exception as e:
            logger.error(f"USER: {user.id} : {user.name} Error sending chunk {index+1}: {e}")
            continue
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=f"Download complete! 💾 🎨"
    )


def custom_json_serializer(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, Enum):
        return obj.value  # Convert Enum instances to their value
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


@check_user_state
async def get_my_user_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"Getting user state for user {user.id} : {user.full_name}")
    user_state = users.get_user_state(user.id)
    user_state_pretty = json.dumps(
        user_state, indent=4, sort_keys=True, default=custom_json_serializer
    )
    user_state_pretty = (
        user_state_pretty.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    out = f"User <code>{user.id}</code> : <b>{user.full_name}</b> is in state:\n<pre>{user_state_pretty}</pre>"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=out,
        parse_mode=constants.ParseMode.HTML,
        reply_to_message_id=update.message.message_id,
    )


@is_admin
@check_user_state
async def get_user_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words_joined = str(" ".join(context.args)).strip().lower()
    logger.info(f"Getting user state for user {words_joined} by ADMIN")
    if users.user_state_exists(words_joined):
        user_state = users.get_user_state(words_joined)
        user_state_pretty = json.dumps(
            user_state, indent=4, sort_keys=True, default=custom_json_serializer
        )
        user_state_pretty = (
            user_state_pretty.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        out = f"User <code>{words_joined}</code> is in state:\n<pre>{user_state_pretty}</pre>"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=out,
            parse_mode=constants.ParseMode.HTML,
        )
    else:
        logger.info(f" -- ADMIN: user '{words_joined}' not found.")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"User '{words_joined}' not found.",
            parse_mode=constants.ParseMode.HTML,
        )


@is_admin
@check_user_state
async def get_all_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    list_of_files = list_images_raw_list()
    logger.info(
        f"User ADMIN is asking for all images.  File count {len(list_of_files)} -- I will let you know when this operation is complete."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"There are {len(list_of_files)} coming in groups of 10.",
    )

    # Function to split the list of files into chunks of 10
    def split_list_in_chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i: i + n]

    # Splitting the list of files into chunks of 10
    chunks_of_files = list(split_list_in_chunks(list_of_files, 10))
    # Iterating over each chunk and sending them as separate media groups

    for index, chunk in enumerate(chunks_of_files):
        media_group = []
        try:
            for file_path in chunk:
                with open(file_path, "rb") as f:
                    media_group.append(InputMediaPhoto(f))
            if media_group:
                logger.info(f"ADMIN IMAGE DOWNLOAD: Sending chunk {index + 1} with {len(media_group)} items.")
                await context.bot.send_media_group(
                    chat_id=update.effective_chat.id, media=media_group
                )
                await asyncio.sleep(10)  # too many per minute?
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id, text="No images found."
                )
                return
        except Exception as e:
            logger.error(f"ADMIN IMAGE DOWNLOAD: Error sending chunk {index + 1}: {e}")
            continue
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text=" 💾 Image download complete. 💾"
    )


@check_user_state
async def pr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text_out = f"👸👸 Hello, pretty pretty princess  👸👸"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text_out)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I didn't understand that command.",
    )


@check_user_state
async def cross_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    words_joined = " ".join(context.args)
    logger.info(f"User ({user.id} | {user.name}) is using /cross")
    if not words_joined == "":
        msg_to_file = f"(Cross Check -> Gemini) {user.username} '{words_joined}' : "
        try:
            # DON'T keep the record.
            users.update_prompt(user.id, users.LLMTypes.BOTH)
            if APP_CONFIG.GEMINI_MODEL == "default":
                words_from_gemini = LLM.google_gemini(words_joined)
            else:
                words_from_gemini = LLM.google_gemini(words_joined, model_to_use=APP_CONFIG.GEMINI_MODEL)
            # limit on how big a msg can be so break it up.
            logger.info(" ++ Gemini sent in /cross")
            with open(APP_CONFIG.CHAT_FILE, "a") as f:
                msg_to_file = msg_to_file + f"CROSS_CHECK->'{words_from_gemini}'"
                f.write(msg_to_file + "\n")
            # logger.info(f" REPLY from Google Gemini (cross check)= {words_from_gemini}")
            new_words = f"Previous, I asked ```{words_joined}``` and got the answer ```{words_from_gemini}```.  Can you improve upon it? please respond with either this answer I already have or a new answer improving upon this answer.  Please don't give a description of the old answer and improvements."
            if APP_CONFIG.CHAT_GPT_MODEL == "default":
                gpt_response = LLM.gpt_4(new_words)
            else:
                gpt_response = LLM.gpt_4(new_words, openAI_model=APP_CONFIG.CHAT_GPT_MODEL)
            logger.info(" ++ ChatGPT sent in /cross")
            # logger.info(f" REPLY from GPT (cross check) = {gpt_response}")
            with open(APP_CONFIG.CHAT_FILE, "a") as f:
                msg_to_file = msg_to_file + f"CROSS_CHECK->'{gpt_response}'"
                f.write(msg_to_file + "\n")
            # This line is to give a user their original answer + the refined one.
            refined = (
                "<b>(unrefined message)</b>: \n"
                + words_from_gemini
                + "\n\n<b>(Revised message)</b>\n"
                + gpt_response
            )
            msgs = [refined[i: i + 4094] for i in range(0, len(refined), 4096)]
            for text_out in msgs:
                # await update.message.reply_text(text=text_out)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text_out,
                    parse_mode=constants.ParseMode.HTML,
                )
            return
        except Exception as e:
            await send_to_admin(
                f"CHAT_COMMAND -(Cross Check)- user: {user.username}:{user.id} got error :{e}",
                context,
            )
            words_joined = "Looks like that's not an allowed prompt.  It's been rejected! (Cross Check)"
            logger.info(f"Error sending chat.  Error: {e}")
    else:
        words_joined = "There was nothing to send to the LLMs.  Try typing \n/cross <i>message here...</i>\nto send a message to Google Gemini."
    with open(APP_CONFIG.CHAT_FILE, "a") as f:
        msg_to_file = f"'{words_joined}'"
        f.write(msg_to_file + "\n")
    await send_to_admin(
        f"CHAT_COMMAND -(Cross Check)- user: {user.username}:{user.id} got error :{words_joined}",
        context,
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=words_joined,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def google_gemini_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    words_joined = " ".join(context.args)
    if not words_joined == "":
        logger.info(f"User {user.name} sending prompt Google Gemini")
        msg_to_file = f"(Google Gemini) {user.username} '{words_joined}' : "
        try:
            # Create a prompt for state-history
            last_prompt = users.get_last_prompt(user.id)
            if last_prompt["prompt"]:
                words_joined_final = f"Last time I asked : ```{last_prompt['prompt']}``` and you replied ```{last_prompt['prompt_result']}```.  ```Now i'm asking {words_joined}```"
            elif last_prompt["prompt_result"]:
                words_joined_final = f"Recently you told me ```{last_prompt['prompt_result']}```.  ```Now i'm asking {words_joined}```"
            else:
                words_joined_final = words_joined
            # add lastest prompt.
            users.update_prompt(
                user.id, UserStates.LLMTypes.GEMINI, prompt=words_joined
            )
            if APP_CONFIG.GEMINI_MODEL == "default":
                words_joined = LLM.google_gemini(words_joined_final)
            else:
                words_joined = LLM.google_gemini(words_joined_final, model_to_use=APP_CONFIG.GEMINI_MODEL)
            # limit on how big a msg can be so break it up.
            with open(APP_CONFIG.CHAT_FILE, "a") as f:
                msg_to_file = msg_to_file + f"'{words_joined}'"
                f.write(msg_to_file + "\n")
            # add latest result.
            users.update_prompt(
                user.id,
                UserStates.LLMTypes.GEMINI,
                prompt_result=words_joined,
                do_not_increase=True,
            )
            msgs = [
                words_joined[i: i + 4094] for i in range(0, len(words_joined), 4096)
            ]
            for text_out in msgs:
                await update.message.reply_text(text=text_out)
            return
        except Exception as e:
            await send_to_admin(
                f"CHAT_COMMAND -(Google Gemini)- user: {user.username}:{user.id} got error :{e}",
                context,
            )
            words_joined = "Looks like that's not an allowed prompt.  It's been rejected! (Google Gemini)"
            logger.info(f"Error sending chat to Google Gemini.  Error: {e}")
    else:
        words_joined = "There was nothing to send to Google Gemini.  Try typing \n/g <i>message here...</i>\nto send a message to Google Gemini."
    with open(APP_CONFIG.CHAT_FILE, "a") as f:
        msg_to_file = f"'{words_joined}'"
        f.write(msg_to_file + "\n")
    await send_to_admin(
        f"CHAT_COMMAND -(Google Gemini)- user: {user.username}:{user.id} got error :{words_joined}",
        context,
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=words_joined,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    # join all the words because the bot sees it as a list of words.
    words_joined = " ".join(context.args)
    if not words_joined == "":
        logger.info(f"User {user.name} sending prompt to chatGPT")
        msg_to_file = f"(ChatGPT) {user.username} '{words_joined}' : "
        temp = 1
        if "t:h" in words_joined:
            words_joined = words_joined.replace("t:h", "")
            temp = 2
        if "t:l" in words_joined:
            words_joined = words_joined.replace("t:l", "")
            temp = 0
        try:
            # Create a prompt for state-history
            last_prompt = users.get_last_prompt(user.id)
            if last_prompt["prompt"]:
                words_joined_final = f"Last time I asked : ```{last_prompt['prompt']}``` and you replied ```{last_prompt['prompt_result']}```.  ```Now i'm asking {words_joined}```"
            elif last_prompt["prompt_result"]:
                words_joined_final = f"Recently you told me ```{last_prompt['prompt_result']}```.  ```Now i'm asking {words_joined}```"
            else:
                words_joined_final = words_joined
            # add lastest prompt.
            users.update_prompt(user.id, UserStates.LLMTypes.GPT, prompt=words_joined)
            if APP_CONFIG.CHAT_GPT_MODEL == "default":
                words_joined = LLM.gpt_4(
                    message=words_joined_final, temp=temp
                )  # Using GPT-4
            else:
                words_joined = LLM.gpt_4(
                    message=words_joined_final, temp=temp, openAI_model=APP_CONFIG.CHAT_GPT_MODEL
                )
            # limit on how big a msg can be so break it up.
            users.update_prompt(
                user.id,
                UserStates.LLMTypes.GPT,
                prompt_result=words_joined,
                do_not_increase=True,
            )
            with open(APP_CONFIG.CHAT_FILE, "a") as f:
                msg_to_file = msg_to_file + f"'{words_joined}'"
                f.write(msg_to_file + "\n")
            msgs = [
                words_joined[i: i + 4094] for i in range(0, len(words_joined), 4096)
            ]
            for text_out in msgs:
                await update.message.reply_text(text=text_out)
            return
        except Exception as e:
            await send_to_admin(
                f"CHAT_COMMAND -- user: {user.username}:{user.id} got error :{e}",
                context,
            )
            words_joined = (
                "Looks like that's not an allowed prompt.  It's been rejected!"
            )
            logger.info(f"Error sending chat to GPT.  Error: {e}")
    else:
        words_joined = "There was nothing to send to ChatGPT.  Try typing \n/c <i>message here...</i>\nto send a message to ChatGPT."
    with open(APP_CONFIG.CHAT_FILE, "a") as f:
        msg_to_file = f"'{words_joined}'"
        f.write(msg_to_file + "\n")
    await send_to_admin(
        f"CHAT_COMMAND -- user: {user.username}:{user.id} got error :{words_joined}",
        context,
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=words_joined,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def dall_e_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    # VERIFY ALLOW
    allowed = user_allowed(str(user.id))
    if not allowed:
        logger.info(
            f"user {user.id}, `{user.full_name}` tried to use /p but isn't allowed."
        )
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Sorry, but you aren't allowed to use this feature.",
            parse_mode=constants.ParseMode.HTML,
        )
        return
    # join all the words because the bot sees it as a list of words.
    words_joined = " ".join(context.args)
    if not words_joined == "":
        logger.info(f"User {user.name} sending to DALL-E")
        msg_to_file = f"(Dall-E) {user.username} '{words_joined}' : "
        try:
            if "size:h" in words_joined:
                size = "1792x1024"
                words_joined = words_joined.replace("size:h", "")
            elif "size:v" in words_joined:
                size = "1024x1792"
                words_joined = words_joined.replace("size:v", "")
            else:
                size = "1024x1024"
            quality = "standard"
            if "q:hd" in words_joined:
                quality = "hd"
                words_joined = words_joined.replace("q:hd", "")
            original_prompt = words_joined
            words_joined = LLM.dall_E_3(words_joined, size=size, quality=quality)
            # Now, save the file incoming.
            save_dir = os.path.join(os.getcwd(), "images")
            filename = (
                str(user.id) + "_" + create_random_filename(20) + ".png"
            )  # GPT returns PNG
            file_save_with_dir = os.path.join(save_dir, filename)
            file_data = requests.get(words_joined)
            with open(file_save_with_dir, "wb") as f:
                f.write(file_data.content)
            # update user prompt for pic
            users.update_pic(user.id, prompt=original_prompt, prompt_result=filename)
            logger.info(f"Saved image from {user.id} : {user.name} as {filename}")
        except Exception as e:
            words_joined = (
                "Looks like that's not an allowed prompt.  It's been rejected!"
            )
            logger.error(f"Rejected attempt to DALL-E: {e}")
            await send_to_admin(
                f"DALL-E_COMMAND -- user: {user.username}:{user.id} got error :{e}",
                context,
            )
        msg_to_file = msg_to_file + f"'{words_joined}'"
        with open(APP_CONFIG.CHAT_FILE, "a") as f:
            f.write(msg_to_file + "\n")
    else:
        words_joined = "There was nothing to send to DALL-E.  Try typing \n/p <i>message here...</i>\nto send a message to DALL-E."
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Your image ({size})\n #images_{user.id}\n <code>{filename}</code>\n " + words_joined,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    logger.info(f"User {user.username} asking for help.")
    command_for_help = ""
    if len(context.args):
        msg_out = context.args
        command_for_help = context.args[0].lower().strip()
        msg_out = f"Sure, {user.username}, i can try help with {command_for_help}.\n"
    if command_for_help:
        logger.info(f"User {user.username} asked for help on {command_for_help}")
        msg_out = help_commands.long_help_by_id(command_for_help)
        if not msg_out:
            logger.info("User didn't send a command to help with.")
            msg_out = "No commands to help with.  After you type /help put the command you want help with after, not including the /."
    else:
        logger.info("User didn't send a command to help with.")
        msg_out = "No commands to help with.  After you type /help put the command you want help with after, not including the /.  type /list for a list of commands."
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    # join all the words because the bot sees it as a list of words.
    words_joined = " ".join(context.args)
    logger.info(f"User ({user.name}, {user.id}) says: {words_joined}")
    await send_to_admin(
        f"#FEEDBACK: {user.username} or ({user.id}) says '{words_joined}'", context
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Thank you for your feedback, {user.username}.",
        parse_mode=constants.ParseMode.HTML,
    )


@check_user_state
async def frog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_msg = "🐸  Frogs?  🐸   I don't 👀 frogs... 🐸🐸 anywhere! 🐸 "
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=help_msg,
        parse_mode=constants.ParseMode.HTML,
    )


async def send_alive_msg(message: str):
    # Start stuff here, like making sure directories exist:
    save_dir = os.path.join(os.getcwd(), "images")
    os.makedirs(save_dir, exist_ok=True)
    await application.bot.send_message(chat_id=APP_CONFIG.ADMIN, text=message)


@is_admin
@check_user_state
async def get_image_by_file_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words_joined = " ".join(context.args)
    if words_joined:
        words_joined = str(words_joined).strip().lower()
        if len(words_joined) > 0:
            filename_request = os.path.join(os.getcwd(), "images", words_joined)
            if os.path.isfile(filename_request):
                logger.info(f"Requested to send file {words_joined}")
                await context.bot.sendPhoto(
                    chat_id=update.effective_chat.id,
                    photo=filename_request,
                    filename=filename_request.split("_")[1],
                    reply_to_message_id=update.message.message_id,
                )
                return
            else:
                msg_out = f"That file doesn't exist '{words_joined}'"
        else:
            msg_out = f"Incorrect file name '{words_joined}'"
    else:
        msg_out = f"Incorrect file name '{words_joined}'"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
        reply_to_message_id=update.message.message_id,
    )


def list_images_raw() -> str:
    try:
        images_dir = os.path.join(os.getcwd(), "images")
        file_list = os.scandir(images_dir)
        out_str = ""
        counter = 0
        for entry in file_list:
            if entry.is_file():
                counter += 1
                out_str += entry.name + "\n"
        return out_str + f"Total images: {counter}\n"
    except Exception as e:
        logger.error(f"Error listing images: {e}")
        return "Error listing images."


def list_images_raw_list() -> list:
    images_dir = os.path.join(os.getcwd(), "images")
    file_list = os.scandir(images_dir)
    out_list = []
    for entry in file_list:
        if entry.is_file():
            path_and_file = os.path.join(images_dir, entry.name)
            out_list.append(path_and_file)
    return out_list


def list_images_by_user(id: str | int) -> str:
    images_dir = os.path.join(os.getcwd(), "images")
    file_list = os.scandir(images_dir)
    out_str = ""
    counter = 0
    for entry in file_list:
        if entry.is_file():
            if entry.name.startswith(str(id).strip()):
                counter += 1
                out_str += entry.name + "\n"
    return out_str + f"Total images: {counter}\n"


def list_images_by_user_as_list(id: str | int) -> list:
    images_dir = os.path.join(os.getcwd(), "images")
    file_list = os.scandir(images_dir)
    out_list = []
    for entry in file_list:
        if entry.is_file():
            if entry.name.startswith(str(id).strip()):
                path_and_file = os.path.join(images_dir, entry.name)
                out_list.append(path_and_file)
    return out_list


def user_allowed(id) -> bool:
    if APP_CONFIG.USE_ALLOW_LIST:
        if id in allow_list.id_list:
            return True
        else:
            return False
    else:
        return True  # if we aren't using the list, always true.


async def give_examples_html(update: Update, context: ContextTypes.DEFAULT_TYPE):
    example_text = """
    <b>bold</b>, <strong>bold</strong>
    <i>italic</i>, <em>italic</em>
    <u>underline</u>, <ins>underline</ins>
    <s>strikethrough</s>, <strike>strikethrough</strike>, <del>strikethrough</del>
    <span class="tg-spoiler">spoiler</span>, <tg-spoiler>spoiler</tg-spoiler>
    <b>bold <i>italic bold <s>italic bold strikethrough <span class="tg-spoiler">italic bold strikethrough spoiler</span></s> <u>underline italic bold</u></i> bold</b>
    <a href="http://www.example.com/">inline URL</a>
    <a href="tg://user?id=123456789">inline mention of a user</a>
    <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>
    <code>inline fixed-width code</code>
    <pre>pre-formatted fixed-width code block</pre>
    <pre><code class="language-python">pre-formatted fixed-width code block written in the Python programming language</code></pre>
    <blockquote>Block quotation started\nBlock quotation continued\nThe last line of the block quotation</blockquote>
    \n\n
    check out : <a href="https://core.telegram.org/bots/api#formatting-options">The official Telegram Guide</a>
    """
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=example_text,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.warn(f" ** Service is restarting! ** ")
        subprocess.Popen(
            [
                "bash",
                "-c",
                f"sleep 5; sudo systemctl restart {TELEGRAM_BOT_SERVICE_NAME}",
            ]
        )
        msg_out = "I'm getting ready to restart 👻 "
    except subprocess.CalledProcessError as e:
        logger.error(f"I was issued a restart but was unable to restart for {e}")
        msg_out = "I was not able to restart 😢 "
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
    )


@is_admin
async def change_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words_joined = " ".join(context.args)
    if not len(context.args):
        msg_out = f"OpenAI Model : <code>{APP_CONFIG.CHAT_GPT_MODEL}</code>\nGemini Model : <code>{APP_CONFIG.GEMINI_MODEL}</code>\n\n ----------------\n"
        msg_out += "To change:\n <code>/model [chatgpt|gemini] [modelname]</code>\n Example:\n <code>/model chatgpt gpt-4o</code>\n"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg_out,
            parse_mode=constants.ParseMode.HTML,
        )
        return
    msg_out = "Changes:\n"
    if "chatgpt" in words_joined.lower():
        logger.info(f"User {update.message.from_user.full_name}|{update.message.from_user.id} changing chatgpt model.")
        APP_CONFIG.CHAT_GPT_MODEL = context.args[-1]
        msg_out += f"ChatGPT model changed to <code>{APP_CONFIG.CHAT_GPT_MODEL}</code>\n"
    elif "gemini" in words_joined.lower():
        logger.info(f"User {update.message.from_user.full_name}|{update.message.from_user.id} changing gemini model.")
        APP_CONFIG.GEMINI_MODEL = context.args[-1]
        msg_out += f"Gemini model changed to <code>{APP_CONFIG.GEMINI_MODEL}</code>\n"
    msg_out += "\n<i>Changes listed above.  You can use /savemodels to make this permanent.</i>"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
    )
    return 

@is_admin
async def save_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The function `save_models` saves changes to OpenAI and Gemini models and provides a summary message.
    """
    msg_out = "Changes:\n"
    openai_done = APP_CONFIG.save_model_change("openai",APP_CONFIG.CHAT_GPT_MODEL)
    gemini_done = APP_CONFIG.save_model_change("gemini",APP_CONFIG.GEMINI_MODEL)
    saved = "✅ saved "
    not_saved =  "🚫 not saved"
    msg_out = f"OpenAI Model : <code>{APP_CONFIG.CHAT_GPT_MODEL}</code>\nGemini Model : <code>{APP_CONFIG.GEMINI_MODEL}</code>\n\n ----------------\n"
    msg_out += f"<code>OPEN_AI</code> = {saved if openai_done else not_saved}\n"
    msg_out += f"<code>GEMINI</code> = {saved if gemini_done else not_saved}\n"
    msg_out += "Remember that these changes are now persistent through reloads."
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
    )
    return 

@is_admin
async def search_models(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words_joined = " ".join(context.args)
    if not len(context.args):
        msg_out = "Search the models for specific text to aid you in changing the model to another model.  Example:\n"
        msg_out += "<code>/searchmodels o3</code> \n -- This would yield all models that contain the text for o3.\n"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg_out,
            parse_mode=constants.ParseMode.HTML,
        )
        return
    msg_out = "Search results:\n"
    gpt_models = LLM.get_openai_models()
    gemini_models = LLM.get_gemini_models()
    pre = r""
    post = r""
    regex = re.compile(fr"{pre}{re.escape(words_joined)}{post}",
                     flags=re.IGNORECASE)   
    msg_out += "\nGPT:\n"
    for model in gpt_models:
        if regex.search(model):
            msg_out += f"{model}\n"
    msg_out += "----------------\n\n"
    msg_out += "\nGemini:\n"
    for model in gemini_models:
        if regex.search(model):
            msg_out += f"{model}\n"
    msg_out += "----------------\n\n"
    msg_out += f"Total models for GPT: {len(gpt_models)}\n"
    msg_out += f"Total modesl for Gemini: {len(gemini_models)}\n"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg_out,
        parse_mode=constants.ParseMode.HTML,
    )
    return


if __name__ == "__main__":

    application = ApplicationBuilder().token(APP_CONFIG.BOT_KEY).build()

    start_handler = CommandHandler("start", start)
    pr_handler = CommandHandler("pr", pr)
    list_handler = CommandHandler("list", list_commands)
    about_me_handler = CommandHandler("aboutme", about_me)
    help_command_handler = CommandHandler("help", help_command)
    frog_handler = CommandHandler("frog", frog)
    unknown_handler = MessageHandler(filters.COMMAND, unknown)
    chatgpt_handler = CommandHandler("c", chat_command)
    google_gemini_handler = CommandHandler("g", google_gemini_chat)
    cross_check_handler = CommandHandler("cross", cross_check)
    dall_e_small_handler = CommandHandler("p", dall_e_command)
    feedback_handler = CommandHandler("feedback", feedback_command)
    memory_status_handler = CommandHandler("mem", memory_status)
    disk_usage_handler = CommandHandler("disk", disk_status)
    cpu_usage_handler = CommandHandler("cpu", cpu_status)
    quote_handler = CommandHandler("q", quote_picker)
    examples_html_handler = CommandHandler("html", give_examples_html)
    admin_helptext_handler = CommandHandler("admin", admin_help_text)
    get_system_status_handler = CommandHandler("sys", get_system_status)
    get_log_lines_handler = CommandHandler("log", get_log_lines)
    view_allow_list_handler = CommandHandler("listusers", list_users)
    add_allow_list_handler = CommandHandler("adduser", add_user)
    remove_alllow_list_handler = CommandHandler("removeuser", remove_user)
    toggle_allow_list_handler = CommandHandler("toggleallow", toggle_allow_list)
    restart_handler = CommandHandler("restart", restart_bot)
    list_all_images_handler = CommandHandler("listallimages", list_all_images)
    get_image_by_file_name_handler = CommandHandler("getimage", get_image_by_file_name)
    get_my_image_list_handler = CommandHandler("listmyimages", list_my_images)
    get_my_image_handler = CommandHandler("getmyimage", get_my_image)
    get_all_my_images_handler = CommandHandler("getallmyimages", get_all_my_images)
    get_all_images_handler = CommandHandler("getallimages", get_all_images)
    get_my_user_state_handler = CommandHandler("getmyuserstate", get_my_user_state)
    get_user_state_handler = CommandHandler("getuserstate", get_user_state)
    get_list_of_user_states_handler = CommandHandler(
        "getuserlist", get_list_of_user_states
    )
    list_all_models_handler = CommandHandler("listmodels", list_all_models)
    change_model_handler = CommandHandler("model", change_model)
    save_models_handler = CommandHandler("savemodels", save_models)
    search_models_handler = CommandHandler("searchmodels", search_models)

    application.add_handler(cpu_usage_handler)
    application.add_handler(disk_usage_handler)
    application.add_handler(memory_status_handler)
    application.add_handler(cross_check_handler)
    application.add_handler(google_gemini_handler)
    application.add_handler(quote_handler)
    application.add_handler(feedback_handler)
    application.add_handler(dall_e_small_handler)
    application.add_handler(chatgpt_handler)
    application.add_handler(start_handler)
    application.add_handler(pr_handler)
    application.add_handler(list_handler)
    application.add_handler(about_me_handler)
    application.add_handler(help_command_handler)
    application.add_handler(frog_handler)
    application.add_handler(examples_html_handler)
    application.add_handler(admin_helptext_handler)
    application.add_handler(get_system_status_handler)
    application.add_handler(get_log_lines_handler)
    application.add_handler(view_allow_list_handler)
    application.add_handler(add_allow_list_handler)
    application.add_handler(remove_alllow_list_handler)
    application.add_handler(toggle_allow_list_handler)
    application.add_handler(restart_handler)
    application.add_handler(list_all_images_handler)
    application.add_handler(get_image_by_file_name_handler)
    application.add_handler(get_my_image_list_handler)
    application.add_handler(get_my_image_handler)
    application.add_handler(get_all_my_images_handler)
    application.add_handler(get_all_images_handler)
    application.add_handler(get_my_user_state_handler)
    application.add_handler(get_user_state_handler)
    application.add_handler(get_list_of_user_states_handler)
    application.add_handler(list_all_models_handler)
    application.add_handler(change_model_handler)
    application.add_handler(save_models_handler)
    application.add_handler(search_models_handler)
    application.add_handler(unknown_handler)

    asyncio.get_event_loop().run_until_complete(
        send_alive_msg(" 🎇 TGram is starting! 😇 ")
    )

    # Get gemini models
    gemini_models = LLM.get_gemini_models()  # get gemini models for printing to log
    logger.info(f"There are {len(gemini_models)} Gemini models and they are : {', '.join(gemini_models)}")

    # Get OpenAI models
    openai_models = LLM.get_openai_models()
    logger.info(f"There are {len(openai_models)} OpenAI models and they are : {', '.join(openai_models)}")

    logger.info(" 🎇 TGram is starting! 😇 ")
    application.run_polling()
