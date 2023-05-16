from glob import glob
import re
import subprocess
import signal
from pathlib import Path
import argparse
import json
import time
import os
import datetime

import tiktoken
import yaml
import openai
import termcolor

def timestamp():
    return datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')

assistant_name = 'assistant'
DEFAULT_CHAT = [
        {"role": "system", "content": "You are a helpful assistant, that answers every question."},
    ]

project_dir = Path(__file__).parent.absolute()
chat_dir = project_dir / "chats"
chat_backup_file = chat_dir / f".backup_{timestamp()}"
config_file = project_dir / "config.yaml"

config = yaml.load(config_file.open(), yaml.FullLoader)
model = config['model']
user = config['user']
speak_lang = config['speak_language']
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
parser.add_argument('--sync-speech', default=speak_default, action='store_true', help='Sync speech with chat')
parser.add_argument('--list-models', action='store_true', help='List all models')
parser.add_argument('--speak', default=speak_default, action='store_true', help='Speak the messages.')
parser.add_argument('--config', action='store_true', help='Open the config file.')
args = parser.parse_args()

class Command:
    def __init__(self, str_matches, description):
        self.str_matches = str_matches
        self.description = description
    def __str__(self) -> str:
        return f"{'/'.join(self.str_matches)}: {self.description}"

class Commands:
    exit = Command(['exit'], 'Exit the program')
    pass_ = Command(['pass'], 'Pass the turn of the current role?')
    clear = Command(['clear'], 'Clear the entire chat (including system message)')
    list = Command(['list', 'ls'], 'List all saved chats')
    list_all = Command(['list all', 'ls all'], 'List all saved chats including hidden backup chats')
    load = Command(['load'], 'Load a chat')
    save = Command(['save'], 'Save the chat')
    edit = Command(['vi', 'vim', 'nvim'], 'Edit the chat')
    regenerate = Command(['regenerate'], 'Regenerate the chat')
    sync = Command(['sync'], 'Sync the chat with the saved chat')
    speak = Command(['speak', 's'], 'Speak the messages')
    speak_en = Command(['speak en', 's en'], 'Speak the messages and set language to english')
    speak_de = Command(['speak de', 's de'], 'Speak the messages and set language to german')
    speak_last = Command(['speak last', 'sl'], 'Speak the last messages')
    help = Command(['help', 'h'], 'Show this help message')
    def __str__(self) -> str:
        return '\n'.join([str(x) for x in [Commands.exit, Commands.pass_, Commands.clear, Commands.list, \
                                            Commands.list_all, Commands.load, Commands.save, Commands.edit, \
                                            Commands.regenerate, Commands.sync, Commands.speak, Commands.speak_en, \
                                            Commands.speak_de, Commands.speak_last, Commands.help]])

commands = Commands()

ctrl_c = 0
def signal_handler(sig, frame):
    global ctrl_c
    ctrl_c += 1

signal.signal(signal.SIGINT, signal_handler)

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

def get_input(prompt):
    try:
        user_input = input(prompt)
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt detected")
        return None
    return user_input

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
        num_tokens += len(enc.encode(e['content'] + ' ' + e['role']))
        if num_tokens > max_tokens:
            break
        new_chat.append(e)
    new_chat = list(reversed(new_chat))
    return [chat[0]] + new_chat, num_tokens

def backup_chat(chat, name=None, prompt_name=None):
    if len(chat) == 0:
        return
    with chat_backup_file.open("w") as f:
        json.dump(chat, f, indent=4)
    if prompt_name:
        try:
            name = get_input("Save name: ")
            with (chat_dir / name).open("w") as f:
                json.dump(chat, f, indent=4)
        except EOFError as e:
            pass
    elif name:
        with (chat_dir / name).open("w") as f:
            json.dump(chat, f, indent=4)

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
    cmd = 'say'
    proc = subprocess.Popen(['which', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.wait()
    if proc.returncode != 0:
        print(f"'say' command not fonud")
        return None

    if speak_lang == 'en':
        return subprocess.Popen([cmd, reading_buffer])
    elif speak_lang == 'de':
        return subprocess.Popen([cmd, '--voice', 'Ann', reading_buffer])
    else:
        raise Exception(f"Unknown language {speak_lang}")

def main():
    global speak_lang
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

    if args.load_chat:
        with (chat_dir / args.load_chat).open() as f:
            chat = json.load(f)
    if args.load_last_chat:
        chat_path = [x for x in sorted(chat_dir.iterdir()) if x.is_file() and x.name.startswith('.backup')][-1]
        with chat_path.open() as f:
            chat = json.load(f)
    else:
        chat = DEFAULT_CHAT

    print_chat(chat)
    active_role = next_role(chat)

    while True:
        if active_role in ['user', 'system'] :
            ctrl_d = 0
            try:
                user_input = get_input(color_role(active_role, f'{user}:\n'))
            except EOFError as e:
                print()
                ctrl_d += 1
            if ctrl_d > 0 or user_input in commands.exit.str_matches:
                backup_chat(chat)
                while not chat_name or chat_name == '':
                    try:
                        chat_name = get_input('Save name: ')
                    except EOFError as e:
                        ctrl_d += 1
                    if ctrl_d > 1 or chat_name in commands.exit.str_matches:
                        exit(0)
                    if (chat_dir / chat_name).exists() and get_input('Chat already exists. Overwrite? ').lower() != 'y':
                            chat_name = ''
                            continue
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f, indent=4)
                exit(0)
            elif user_input in commands.pass_.str_matches:
                active_role = "assistant"
                continue
            elif user_input in commands.clear.str_matches:
                backup_chat(chat)
                chat = []
                active_role = next_role(chat)
                print('\n\n')
                continue
            elif user_input in commands.list.str_matches:
                for chars in chat_dir.iterdir():
                    if not chars.name.startswith('.'):
                        print(f"{chars.name}")
                continue
            elif user_input in commands.list_all.str_matches:
                for chars in chat_dir.iterdir():
                    print(f"{chars.name}")
                continue
            elif user_input in commands.load.str_matches:
                for chars in chat_dir.iterdir():
                    if not chars.name.startswith('.'):
                        print(f"{chars.name}")
                chat_name = get_input('Name of chat to load: ')
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
                    chat_name = get_input('Name chat: ').strip()
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
            elif user_input in commands.sync.str_matches:
                args.sync_speech = not args.sync_speech
                print(f"Sync speech: {args.sync_speech}")
                continue
            elif user_input in commands.speak.str_matches:
                args.speak = not args.speak
                args.sync_speech = args.speak
                print(f"Speak messages: {args.speak}, Sync speech: {args.sync_speech}, language: {speak_lang}")
                continue
            elif user_input in commands.speak_en.str_matches:
                args.speak = True
                args.sync_speech = True
                speak_lang = 'en'
                print(f"Speak messages: {args.speak}, Sync speech: {args.sync_speech}, language: {speak_lang}")
                continue
            elif user_input in commands.speak_de.str_matches:
                args.speak = True
                args.sync_speech = True
                speak_lang = 'de'
                print(f"Speak messages: {args.speak}, Sync speech: {args.sync_speech}, language: {speak_lang}")
                continue
            elif user_input in commands.help.str_matches:
                print(commands)
                continue
            elif user_input in commands.speak_last.str_matches:
                speak(chat[-1]['content'])
                continue
            append_to_chat(chat, active_role, user_input)
            backup_chat(chat)
            active_role = next_role(chat)
        elif active_role == 'assistant':
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

                if not args.sync_speech:
                    print(c, end='', flush=True)

                if speak_subproc is None or speak_subproc.poll() is not None:
                    for i,chars in enumerate(read_buffer):
                        if chars in ['.', '?', '!']:
                            reading_buffer = read_buffer[:i+1]
                            read_buffer = read_buffer[i+1:]
                            if args.speak:
                                speak_subproc = speak(reading_buffer)
                                if args.sync_speech:
                                    print(reading_buffer, end='', flush=True)
                            break
                
                if ctrl_c > 0:
                    ctrl_c = 0
                    break

            # Speak the remaning buffer
            while True:
                if args.speak and (speak_subproc == None or speak_subproc.poll() is not None):
                    speak_subproc = speak(read_buffer)
                    if args.sync_speech:
                        print(read_buffer, end='', flush=True)
                    break

            print()
            complete_response = ''.join(complete_response)
            append_to_chat(chat, 'assistant', complete_response)
            active_role = next_role(chat)

if __name__ == "__main__":
    main()