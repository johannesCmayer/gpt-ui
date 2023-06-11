from glob import glob
import hashlib
import re
import subprocess
import signal
from pathlib import Path
import argparse
import json
import time
import os
import datetime
import sys
from copy import deepcopy

import tiktoken
import yaml
import openai
import termcolor

def timestamp():
    return datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')

assistant_name = 'assistant'
def GET_DEFAULT_CHAT(): 
    return deepcopy([
        {"role": "system", "content": "You are a helpful assistant, that answers every question."},
    ])

project_dir = Path(__file__).parent.absolute()
chat_dir = project_dir / "chats"
chat_backup_file = chat_dir / f".backup_{timestamp()}"
config_file = project_dir / "config.yaml"

config = yaml.load(config_file.open(), yaml.FullLoader)
model = config['model']
user = config['user']
max_tokens_dict = { 'gpt-4': 8192 }
max_tokens = max_tokens_dict[model]
speak_default = config['speak']

openai.api_key = yaml.load((project_dir / 'api_key.yaml').open(), yaml.FullLoader).get('api_key')
enc = tiktoken.encoding_for_model(model)

parser = argparse.ArgumentParser(usage=
                                   ("\nPress CTRL+C to stop generating the message.\n"
                                    "In user role press CTRL+D to exit the chat. You will first be asked to save the chat.\n"
                                    "Press CTRL+D in the safe dialog to exit the program without saving the chat.\n"
                                    "Enter 'help' as the user role to see all commands you can enter in the user role."))
parser.add_argument('--chat-name', type=str, help='Name of the chat')
parser.add_argument('--load-chat', type=str, help='Name of the chat to load')
parser.add_argument('--load-last-chat', action='store_true', help='Name of the chat to load')
parser.add_argument('--list-chats', action='store_true', help='List all chats')
parser.add_argument('--list-all-chats', action='store_true', help='List all chats including hidden backup chats')
parser.add_argument('--list-models', action='store_true', help='List all models')
parser.add_argument('--speak', default=speak_default, action='store_true', help='Speak the messages.')
parser.add_argument('--config', action='store_true', help='Open the config file.')
parser.add_argument('--debug', action='store_true', help='Run with debug settings. Includes notifications.')
parser.add_argument('user_input',  type=str, nargs='*', help='Initial input the user gives to the chat bot.')
args = parser.parse_args()
if args.user_input == []:
    args.user_input = None
else:
    args.user_input = " ".join(args.user_input)
    if args.user_input == "":
        args.user_input = None

class Command:
    def __init__(self, str_matches, description):
        self.str_matches = str_matches
        self.description = description
    def __str__(self) -> str:
        return f"{'/'.join(self.str_matches)}: {self.description}"

class Commands:
    exit = Command(['exit'], 'Exit the program')
    pass_ = Command(['pass'], 'Pass the turn of the current role?')
    restart = Command(['restart'], 'Clear the entire chat (excluding system message)')
    restart_hard = Command(['restart hard'], 'Clear the entire chat (including system message)')
    list = Command(['list', 'ls'], 'List all saved chats')
    list_all = Command(['list all', 'ls all'], 'List all saved chats including hidden backup chats')
    load = Command(['load'], 'Load a chat')
    save = Command(['save'], 'Save the chat')
    edit = Command(['vi', 'vim', 'nvim'], 'Edit the chat')
    regenerate = Command(['regenerate'], 'Regenerate the chat')
    speak = Command(['speak', 's'], 'Speak the messages')
    speak_last = Command(['speak last', 'sl'], 'Speak the last messages')
    help = Command(['help', 'h'], 'Show this help message')
    def __str__(self) -> str:
        return '\n'.join([str(x) for x in [Commands.exit, Commands.pass_, Commands.restart, Commands.restart_hard, Commands.list, \
                                            Commands.list_all, Commands.load, Commands.save, Commands.edit, \
                                            Commands.regenerate, Commands.speak, Commands.speak_last, \
                                            Commands.help]])

commands = Commands()

ctrl_c = 0
def signal_handler(sig, frame):
    global ctrl_c
    ctrl_c += 1

signal.signal(signal.SIGINT, signal_handler)

def di_print(s):
    s = termcolor.colored(s, "red")
    print(f"<{s}>", end='', flush=True)

def color_role(s, s2=None):
    if "system" in s:
        return termcolor.colored(s2 if s2 else s, "red")
    elif "user" in s:
        return termcolor.colored(s2 if s2 else s, "green")
    else:
        return termcolor.colored(s2 if s2 else s, "blue")

def next_role(chat):
    if len(chat) == 0:
        return "system"
    elif chat[-1]["role"] == "user":
        return "assistant"
    else:
        return "user"

def print_chat(chat):
    for m in chat:
        name = m['model'] if m['role'] == 'assistant' else (m['user'] if m['role'] == 'user' else 'system')
        print(f"{color_role(m['role'], name)}:\n{m['content']}")

def append_to_chat(chat, role, content, l_date=None, l_model=None, l_user=None):
    date = timestamp()
    chat.append({"role": role, "model": l_model if l_model else model, 'user': l_user if l_user else user, 'date': l_date if l_date else date, "content": content})
    backup_chat(chat)

def trim_chat(chat):
    num_tokens = len(enc.encode(chat[0]['content']))
    new_chat = []
    for i, e in enumerate(reversed(chat[1:])):
        num_tokens += len(enc.encode(e['content']))
        if num_tokens > max_tokens:
            break
        new_chat.append(e)
    new_chat = list(reversed(new_chat))
    return [chat[0]] + new_chat, num_tokens

def backup_chat(chat, name=None, prompt_name=None):
    if len(chat) == 0:
        return
    # Always backup chat, even if name will be provided
    with chat_backup_file.open("w") as f:
        json.dump(chat, f, indent=4)
    if prompt_name:
        try:
            user_input_name = input("Save name: ")
            with (chat_dir / user_input_name).open("w") as f:
                json.dump(chat, f, indent=4)
            return user_input_name
        except EOFError as e:
            pass
    elif name:
        with (chat_dir / name).open("w") as f:
            json.dump(chat, f, indent=4)
        return name
    else:
        return chat_backup_file

def edit_chat(chat, user_input):
    backup_chat(chat)
    meta_data_prefix = f"###>>>"
    with (chat_dir / 'temp').open("w") as f:
        for m in chat:
            meta_data = json.dumps({k: v for k, v in m.items() if k != 'content'})
            f.write(f"{meta_data_prefix}{meta_data}\n{m['content']}\n\n")
        meta_data = json.dumps({'role': next_role(chat), 'model': model, 'user': user, 'date': timestamp()})
        f.write(f"{meta_data_prefix}{meta_data}\n\n")
    os.system(f"{user_input} {chat_dir / 'temp'}")
    with (chat_dir / 'temp').open() as f:
        chat = []
        role = None
        text = ""
        last_r = None
        for line in f:
            r = None
            if line.startswith(meta_data_prefix):
                r = json.loads(line[len(meta_data_prefix):])
                last_r = r
            if r:
                if role:
                    append_to_chat(
                        chat, 
                        role, 
                        text.strip(), 
                        l_date=r['date'] if r and 'date' in r else None, 
                        l_user=r['user'] if r and 'user' in r else None,
                        l_model=r['model'] if r and 'model' in r else None)
                backup_chat(chat)
                text = ""
                role = r['role']
            else:
                text += line
        if text.strip() != "":
            append_to_chat(
                chat, 
                role, 
                text.strip(), 
                l_date=last_r['date'] if 'date' in last_r else None, 
                l_user=last_r['user'] if 'user' in last_r else None,
                l_model=last_r['model'] if 'model' in last_r else None)
        backup_chat(chat)
    (chat_dir / 'temp').unlink()
    print('\n\n')
    print_chat(chat)
    return chat

def speak(reading_buffer):
    cmd = 'gsay'
    proc = subprocess.Popen(['which', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    if proc.returncode != 0:
        print(f"{cmd} not found")
        return None

    reading_buffer = re.sub('`', '', reading_buffer)
    # Filter out python interpreter prompt
    reading_buffer = re.sub('>>> ', '', reading_buffer)
    # Filter out underscores
    reading_buffer = re.sub('_', ' ', reading_buffer)
    reading_buffer = reading_buffer.strip()
    debug_notify(reading_buffer)
    subprocess.Popen([cmd, "--", reading_buffer], stderr=subprocess.PIPE, stdout=subprocess.PIPE)

def speak_first_sentence(text):
    """Split the text and speak the first sentence, if one exists
       and then speak it. Return the leftover text.
    """
    end_chars = ['.', '?', '!', ':', '。', '？', '！']
    end_markers = []
    for c in end_chars:
        end_markers.append(c + ' ')
        end_markers.append(c + '\n')
        end_markers.append(c + '"')
        end_markers.append(c + "'")

    for i in range(len(text)):
        if text[i] == '\n' or (len(text) >= 2 and text[i:i+2] in end_markers):
            target_text = text[:i+1]
            text = text[i+1:]
            if args.speak:
                speak(target_text)
            break
    return text

def speak_all_as_sentences(text):
    hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    last_hash = None
    while hash != last_hash:
        text = speak_first_sentence(text)
        last_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        hash = hashlib.md5(text.encode('utf-8')).hexdigest()
    speak(text)

def main():
    if args.list_models:
        print('available models:')
        for m in sorted(openai.Model.list()['data'], key=lambda x: x['id']): 
            print(m['id'])
        exit(0)

    global ctrl_c
    chat_name = args.chat_name

    if args.list_chats or args.list_all_chats:
        for chars in sorted(chat_dir.iterdir()):
            if args.list_all_chats or not chars.name.startswith('.'):
                print(f"{chars.name}")
        exit(0)
    elif args.config:
        os.system(f"vi {config_file}")
        exit(0)

    if args.user_input:
        chat = GET_DEFAULT_CHAT()
        chat.append({'role': 'user', 'content': args.user_input, 'user': config['user']})
    elif args.load_chat:
        with (chat_dir / args.load_chat).open() as f:
            chat = json.load(f)
    elif args.load_last_chat:
        chat_path = [x for x in sorted(chat_dir.iterdir()) if x.is_file() and x.name.startswith('.backup')][-1]
        with chat_path.open() as f:
            chat = json.load(f)
    else:
        chat = GET_DEFAULT_CHAT()

    print_chat(chat)

    active_role = next_role(chat)

    while True:
        if active_role in ['user', 'system'] :
            di_print("enter user role")
            ctrl_d = 0
            try:
                di_print("try to get user input")
                user_input = input(color_role(active_role, f'{user if active_role == "user" else "system"}:\n'))
                di_print("got user input successfull")
            except EOFError as e:
                di_print(str(e))
                di_print("user input error (ctrl+d press is likely)")
                print()
                ctrl_d += 1
            di_print("begin match user input")
            if ctrl_d > 0 or user_input in commands.exit.str_matches:
                backup_chat_name = backup_chat(chat)
                while not chat_name or chat_name == '':
                    try:
                        chat_name = input('Save name: ')
                    except EOFError as e:
                        ctrl_d += 1
                    if ctrl_d > 1 or chat_name in commands.exit.str_matches:
                        print(f"Chat saved as: {backup_chat_name}")
                        exit(0)
                    if (chat_dir / chat_name).exists() and input('Chat already exists. Overwrite? ').lower() != 'y':
                            chat_name = ''
                            continue
                    time.sleep(0.1)
                chat_save_name = backup_chat(chat, chat_name)
                print(f"Chat saved as: {chat_save_name}")
                exit(0)
            elif user_input in commands.pass_.str_matches:
                active_role = "assistant"
                continue
            elif user_input in commands.restart.str_matches:
                backup_chat(chat)
                chat = GET_DEFAULT_CHAT()
                print('\n\n')
                print_chat(chat)
                active_role = next_role(chat)
                continue
            elif user_input in commands.restart_hard.str_matches:
                backup_chat(chat)
                print('\n\n')
                chat = []
                active_role = next_role(chat)
                continue
            elif user_input in commands.list.str_matches:
                for chars in sorted(chat_dir.iterdir()):
                    if not chars.name.startswith('.'):
                        print(f"{chars.name}")
                continue
            elif user_input in commands.list_all.str_matches:
                for chars in sorted(chat_dir.iterdir()):
                    print(f"{chars.name}")
                continue
            elif user_input in commands.load.str_matches:
                for chars in chat_dir.iterdir():
                    if not chars.name.startswith('.'):
                        print(f"{chars.name}")
                chat_name = input('Name of chat to load: ')
                if chat_name == 'exit':
                    continue
                with chat_dir.joinpath(chat_name).open() as f:
                    backup_chat(chat)
                    chat = json.load(f)
                print('\n\n')
                print_chat(chat)
                continue 
            elif user_input in commands.save.str_matches:
                while not chat_name or (chat_dir / chat_name).exists() or chat_name == '':
                    chat_name = input('Name chat: ').strip()
                    if chat_name == 'exit':
                        continue
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f, indent=4)
                continue
            elif user_input in commands.edit.str_matches:
                chat = edit_chat(chat, user_input)
                continue
            elif len(chat) >= 3 and user_input in commands.regenerate.str_matches:
                backup_chat(chat)
                chat = chat[:-1]
                active_role = next_role(active_role)
                print('\n\n')
                print_chat(chat)
                continue
            elif user_input in commands.speak.str_matches:
                args.speak = not args.speak
                print(f"Speak messages: {args.speak}")
                continue
            elif user_input in commands.help.str_matches:
                print(commands)
                continue
            elif user_input in commands.speak_last.str_matches:
                speak_all_as_sentences(chat[-1]['content'])
                continue
            append_to_chat(chat, active_role, user_input)
            backup_chat(chat)
            active_role = next_role(chat)
        elif active_role == 'assistant':
            # Get the content iterator
            chat, num_tokens = trim_chat(chat)
            max_retries = 5
            n_max_retries = 0
            for i in range(max_retries):
                try:
                    response = openai.ChatCompletion.create(
                        model=model,
                        messages=[{k: v for k, v in y.items() if k in ['role', 'content']} for y in chat],
                        stream = True,
                    )
                    break
                except Exception as e:
                    print(f"try {n_max_retries}/{max_retries}")
                    print(f"Error: {e}")
                    if n_max_retries >= max_retries:
                        backup_chat(chat)
                        raise {e}
                    n_max_retries += 1
                    time.sleep(1)
            complete_response = []
            print(color_role(f'{int(num_tokens/max_tokens*100)}% {model}:\n'), end='', flush=True)

            # Process the content
            read_buffer = ''
            speak_subproc = None
            for chunk in response:
                c = None
                try:
                    c = chunk.choices[0].delta.content
                    complete_response.append(c)
                    read_buffer += c
                except AttributeError as e:
                    pass
                except Exception as e:
                    print("\nAn error occured.")
                    backup_chat(chat, prompt_name=True)
                    raise e

                if c is None:
                    continue

                print(c, end='', flush=True)

                # if speak_subproc is None or speak_subproc.poll() is not None:
                read_buffer = speak_first_sentence(read_buffer)
                
                if ctrl_c > 0:
                    ctrl_c = 0
                    break

            # Speak the remaning buffer
            speak_all_as_sentences(read_buffer)

            print()
            complete_response = ''.join(complete_response)
            append_to_chat(chat, 'assistant', complete_response)
            active_role = next_role(chat)
    
def debug_notify(msg):
    if args.debug:
        os.system(f"notify-send '{msg}'")

if __name__ == "__main__":
    main()
