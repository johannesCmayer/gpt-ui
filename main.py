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
import readline

import tiktoken
import yaml
import openai
import termcolor

model = 'gpt-4'
user = 'Johannes'
max_tokens = 8192
assistant_name = 'assistant'
default_chat = [
        {"role": "system", "content": "You are a helpful assistant, that answers every question."},
    ]

project_dir = Path(__file__).parent.absolute()
chat_dir = project_dir / "chats"
chat_backup_file = chat_dir / f".backup_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"

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
parser.add_argument('--sync-speech', default=False, action='store_true', help='Sync speech with chat')
parser.add_argument('--list-models', action='store_true', help='List all models')
parser.add_argument('--speak', default=False, action='store_true', help='Speak the messages.')
args = parser.parse_args()

def backup_chat(chat, name=None, prompt_name=None):
    if chat == default_chat or len(chat) == 0:
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

def color_role(s, s2=None):
    if "system" in s:
        return termcolor.colored(s2 if s2 else s, "red")
    elif "user" in s:
        return termcolor.colored(s2 if s2 else s, "green")
    else:
        return termcolor.colored(s2 if s2 else s, "blue")

def print_chat(chat):
    for m in chat:
        name = m['model'] if m['role'] == 'assistant' else (m['user'] if m['role'] == 'user' else 'system')
        print(f"{color_role(m['role'], name)}: {m['content']}")

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

ctrl_c = 0
def signal_handler(sig, frame):
    global ctrl_c
    ctrl_c += 1

signal.signal(signal.SIGINT, signal_handler)

def trim_chat(chat):
    num_tokens = 0
    for i, e in enumerate(reversed(chat)):
        num_tokens += len(enc.encode(e['content']))
        if num_tokens > max_tokens:
            return list(reversed(reversed(chat)[:i])), num_tokens
    return chat, num_tokens

def append_to_chat(chat, role, content, l_date=None, l_model=None, l_user=None):
    date = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    chat.append({"role": role, "model": l_model if l_model else model, 'user': l_user if l_user else user, 'date': l_date if l_date else date, "content": content})
    backup_chat(chat)


def main():
    if args.list_models:
        print('available models:')
        for m in sorted(openai.Model.list()['data'], key=lambda x: x['id']): 
            print(m['id'])
        exit(0)

    global ctrl_c
    chat_name = args.chat_name

    if args.list_chats or args.list_all_chats:
        for c in chat_dir.iterdir():
            if args.list_all_chats or not c.name.startswith('.'):
                print(f"{c.name}")
        exit(0)

    if args.load_chat:
        with (chat_dir / args.load_chat).open() as f:
            chat = json.load(f)
    if args.load_last_chat:
        chat_path = [x for x in sorted(chat_dir.iterdir()) if x.is_file() and x.name.startswith('.')][-1]
        with chat_path.open() as f:
            chat = json.load(f)
    else:
        chat = default_chat

    print_chat(chat)
    active_role = next_role(chat)

    while True:
        if active_role in ['user', 'system'] :
            ctrl_d = 0
            try:
                user_input = get_input(color_role(active_role, f'{user}: '))
            except EOFError as e:
                print()
                ctrl_d += 1
            if ctrl_d > 0 or user_input == 'exit':
                backup_chat(chat)
                while not chat_name or chat_name == '':
                    try:
                        chat_name = get_input('Save name: ')
                    except EOFError as e:
                        ctrl_d += 1
                    if ctrl_d > 1 or chat_name == 'exit':
                        exit(0)
                    if (chat_dir / chat_name).exists() and get_input('Chat already exists. Overwrite? ').lower() != 'y':
                            chat_name = ''
                            continue
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f, indent=4)
                exit(0)
            elif user_input in ['pass']:
                active_role = "assistant"
                continue
            elif user_input in ['clear', 'cls']:
                backup_chat(chat)
                chat = []
                active_role = next_role(chat)
                print('\n\n')
                continue
            elif user_input in ['list', 'ls']:
                for c in chat_dir.iterdir():
                    if not c.name.startswith('.'):
                        print(f"{c.name}")
                continue
            elif user_input in ['list all', 'lsa']:
                for c in chat_dir.iterdir():
                    print(f"{c.name}")
                continue
            elif user_input in ['load', 'ld']:
                for c in chat_dir.iterdir():
                    if not c.name.startswith('.'):
                        print(f"{c.name}")
                chat_name = get_input('Name of chat to load: ')
                if chat_name == 'exit':
                    continue
                with chat_dir.joinpath(chat_name).open() as f:
                    backup_chat(chat)
                    chat = json.load(f)
                print('\n\n')
                print_chat(chat)
                continue 
            elif user_input in ['save', 'sv']:
                while not chat_name or (chat_dir / chat_name).exists() or chat_name == '':
                    chat_name = get_input('Name chat: ').strip()
                    if chat_name == 'exit':
                        continue
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f, indent=4)
                continue
            elif user_input in ['vi', 'vim', 'nvim']:
                backup_chat(chat)
                with (chat_dir / 'temp').open("w") as f:
                    for m in chat:
                        prefix = json.dumps({k: v for k, v in m.items() if k != 'content'})
                        f.write(f"{prefix}\n{m['content']}\n\n")
                os.system(f"{user_input} {chat_dir / 'temp'}")
                with (chat_dir / 'temp').open() as f:
                    chat = []
                    role = None
                    text = ""
                    last_r = None
                    for line in f:
                        r = None
                        try:
                            r = json.loads(line)
                            last_r = r
                        except:
                            pass
                        if r:
                            if role:
                                append_to_chat(chat, 
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
                    append_to_chat(chat, 
                                    role, 
                                    text.strip(), 
                                    l_date=last_r['date'] if 'date' in last_r else None, 
                                    l_user=last_r['user'] if 'user' in last_r else None,
                                    l_model=last_r['model'] if 'model' in last_r else None)
                    backup_chat(chat)
                (chat_dir / 'temp').unlink()
                print('\n\n')
                print_chat(chat)
                continue
            elif len(chat) >= 3 and user_input in ['regenerate', 'regen']:
                backup_chat(chat)
                chat = chat[:-1]
                active_role = next_role(active_role)
                print('\n\n')
                print_chat(chat)
                continue
            elif user_input in ['sync', 'sy']:
                args.sync_speech = not args.sync_speech
                print(f"Sync speech: {args.sync_speech}")
                continue
            elif user_input in ['help', 'h']:
                print('''
                exit: exit the chat
                regen: regenerate the last assistant message
                clear: clear the chat
                list/ls: list chats
                list all/lsa: list all chats including hidden backup chats
                load/ld: load a chat
                save/sv: save the chat
                vim/vi/nvim: edit the chat with the corresponding command
                sync/sy: toggle sync speech
                help/h: show this message
                ''')
                continue
            append_to_chat(chat, active_role, user_input)
            backup_chat(chat)
            active_role = next_role(chat)
        elif active_role == 'assistant':
            while True:
                chat, num_tokens = trim_chat(chat)
                try:
                    response = openai.ChatCompletion.create(
                        model=model,
                        messages=[{k: v for k, v in y.items() if k in ['role', 'content']} for y in chat],
                        stream = True,
                    )
                    break
                except Exception as e:
                    backup_chat(chat)
                    raise {e}
            complete_response = []
            print(color_role(f'{int(num_tokens/max_tokens*100)}% {model}: '), end='', flush=True)
            read_buffer = ''
            subpc = None
            for chunk in response:
                try:
                    c = chunk.choices[0].delta.content
                    if not args.sync_speech:
                        print(c, end='', flush=True)
                    complete_response.append(c)
                    read_buffer += c
                    if ctrl_c > 0:
                        ctrl_c = 0
                        break
                except AttributeError as e:
                    pass
                except Exception as e:
                    print("\nAn error occured.")
                    backup_chat(chat, prompt_name=True)
                    raise e
                    
                if subpc is None or subpc.poll() is not None:
                    for i,c in enumerate(read_buffer):
                        if c in ['. ', '? ', '! ', '\n']:
                            reading_buffer = read_buffer[:i+1]
                            read_buffer = read_buffer[i+1:]
                            if args.speak:
                                subpc = subprocess.Popen(['say', reading_buffer])
                                if args.sync_speech:
                                    print(reading_buffer, end='', flush=True)
                                break
            while read_buffer != '':
                if subpc is None or subpc.poll() is not None:
                    for i,c in enumerate(read_buffer):
                        if c in ['.', '?', '!']:
                            reading_buffer = read_buffer[:i+1]
                            read_buffer = read_buffer[i+1:]
                            if args.speak:
                                subpc = subprocess.Popen(['say', reading_buffer])
                                if args.sync_speech:
                                    print(reading_buffer, end='', flush=True)
                            break
                    else:
                        break
            print()
            complete_response = ''.join(complete_response)
            append_to_chat(chat, 'assistant', complete_response)
            active_role = next_role(chat)

if __name__ == "__main__":
    main()