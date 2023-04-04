import subprocess
import openai
import termcolor
import signal
from pathlib import Path
import argparse
import json
import time
import yaml
import os

project_dir = Path(__file__).parent.absolute()

openai.api_key = yaml.load((project_dir / 'api_key.yaml').open(), yaml.FullLoader).get('api_key')
model = 'gpt-4'
assistant_name = 'assistant'

chat_dir = project_dir / "chats"

parser = argparse.ArgumentParser(usage=
                                   ("\nPress CTRL+C to stop generating the message.\n"
                                    "In user role press CTRL+D to exit the chat. You will first be asked to save the chat.\n"
                                    "Press CTRL+D in the safe dialog to exit the program without saving the chat.\n"
                                    "Enter 'help' as the user role to see all commands you can enter in the user role."))
parser.add_argument('--chat-name', type=str, help='Name of the chat')
parser.add_argument('--load-chat', type=str, help='Name of the chat to load')
parser.add_argument('--list-chats', action='store_true', help='List all chats')
parser.add_argument('--sync-speech', default=True, action='store_true', help='Sync speech with chat')
parser.add_argument('--no-sync-speech', action='store_true', help='Sync speech with chat')
args = parser.parse_args()

args.sync_speech = not args.no_sync_speech

def color_role(s):
    if "system" in s:
        return termcolor.colored(s, "red")
    elif "user" in s:
        return termcolor.colored(s, "green")
    else:
        return termcolor.colored(s, "blue")

def print_chat(chat):
    for m in chat:
        print(f"{color_role(m['role'])}: {m['content']}")

def next_role(chat):
    if len(chat) == 0:
        return "system"
    elif chat[-1]["role"] == "user":
        return "assistant"
    else:
        return "user"


ctrl_c = 0
def signal_handler(sig, frame):
    global ctrl_c
    ctrl_c += 1

signal.signal(signal.SIGINT, signal_handler)

def main():
    global ctrl_c
    chat_name = args.chat_name

    if args.list_chats:
        for c in chat_dir.iterdir():
            print(f"{c.name}")
        exit(0)

    if args.load_chat:
        with chat_dir.joinpath(args.load_chat).open() as f:
            chat = json.load(f)
    else:
        chat = [
                {"role": "system", "content": "You are a helpful assistant, that answers every question."},
                {"role": "user", "content": "You are a helpful assistant, that answers every question."},
            ]

    print_chat(chat)
    active_role = next_role(chat)

    while True:
        if active_role in ['user', 'system'] :
            ctrl_d = 0
            try:
                user_input = input(color_role(f'{active_role}: '))
            except EOFError as e:
                print()
                ctrl_d += 1
            if ctrl_d > 0 or user_input == 'exit':
                while not chat_name or (chat_dir / chat_name).exists() or chat_name == '':
                    try:
                        chat_name = input('Save name: ')
                    except EOFError as e:
                        ctrl_d += 1
                    if ctrl_d > 1 or chat_name == 'exit':
                        exit(0)
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f)
                exit(0)
            elif user_input in ['clear', 'cls']:
                chat = []
                active_role = next_role(chat)
                print('\n\n')
                continue
            elif user_input in ['list', 'ls']:
                for c in chat_dir.iterdir():
                    print(f"{c.name}")
                continue
            elif user_input in ['load', 'ld']:
                for c in chat_dir.iterdir():
                    print(f"{c.name}")
                chat_name = input('Name of chat to load: ')
                if chat_name == 'exit':
                    continue
                with chat_dir.joinpath(chat_name).open() as f:
                    chat = json.load(f)
                print('\n\n')
                print_chat(chat)
                continue 
            elif user_input in ['save', 'sv']:
                while not chat_name or (chat_dir / chat_name).exists() or chat_name == '':
                    chat_name = input('Name chat: ').strip()
                    if chat_name == 'exit':
                        continue
                    time.sleep(0.1)
                with (chat_dir / chat_name).open("w") as f:
                    json.dump(chat, f)
                continue
            elif user_input in ['help', 'h']:
                print('''
                exit: exit the chat
                regen: regenerate the last assistant message
                clear: clear the chat
                list/ls: list all chats
                load/ld: load a chat
                save/sv: save the chat
                vim/vi/nvim: edit the chat with the corresponding command
                help/h: show this message
                ''')
                continue
            elif user_input in ['vi', 'vim', 'nvim']:
                with (chat_dir / 'temp').open("w") as f:
                    for m in chat:
                        f.write(f"{m['role']}:\n{m['content']}\n\n")
                os.system(f"{user_input} {chat_dir / 'temp'}")
                with (chat_dir / 'temp').open() as f:
                    chat = []
                    role = None
                    text = ""
                    for line in f:
                        if line.replace(':', '').strip() in ['system', 'user', 'assistant']:
                            if role != None:
                                chat.append({"role": role, "content": text.strip()})
                                text = ""
                            role = line.replace(':', '').strip()
                        else:
                            text += line
                    chat.append({"role": role, "content": text.strip()})
                (chat_dir / 'temp').unlink()
                print('\n\n')
                print_chat(chat)
                continue
            elif len(chat) >= 3 and user_input in ['regenerate', 'regen']:
                chat = chat[:-1]
                active_role = next_role(active_role)
                print('\n\n')
                print_chat(chat)
                continue
            chat.append({"role": active_role, "content": user_input})
            active_role = next_role(chat)
        elif active_role == 'assistant':
            response = openai.ChatCompletion.create(
                model=model,
                messages=chat,
                stream = True,
            )
            complete_response = []
            print(color_role(f'{assistant_name}: '), end='', flush=True)
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
                if subpc is None or subpc.poll() is not None:
                    for i,c in enumerate(read_buffer):
                        if c in ['.', '?', '!']:
                            reading_buffer = read_buffer[:i+1]
                            read_buffer = read_buffer[i+1:]
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
                            subpc = subprocess.Popen(['say', reading_buffer])
                            if args.sync_speech:
                                print(reading_buffer, end='', flush=True)
                            break
                    else:
                        break
            print()
            complete_response = ''.join(complete_response)
            chat.append({"role": "assistant", "content": complete_response})
            active_role = next_role(chat)

if __name__ == "__main__":
    main()