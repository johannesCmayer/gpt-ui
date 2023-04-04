import openai
import termcolor
import signal
from pathlib import Path
import argparse
import json
import time
import yaml

project_dir = Path(__file__).parent.absolute()

openai.api_key = yaml.load((project_dir / 'api_key.yaml').open(), yaml.FullLoader).get('api_key')
model = 'gpt-4'
assistant_name = 'assistant'

chat_dir = project_dir / "chats"

chat_name = ''

def signal_handler(sig, frame):
    print("Ctrl+C disabeled! Use the 'exit' command instead.")

signal.signal(signal.SIGINT, signal_handler)

parser = argparse.ArgumentParser(description='Chat with OpenAI GPT-4')
parser.add_argument('--chat-name', type=str, help='Name of the chat')
parser.add_argument('--load-chat', type=str, help='Name of the chat to load')
parser.add_argument('--list-chats', action='store_true', help='List all chats')
args = parser.parse_args()

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
        ]

def color_role(s):
    if "system" in s:
        return termcolor.colored(s, "grey")
    elif "user" in s:
        return termcolor.colored(s, "green")
    else:
        return termcolor.colored(s, "blue")

def print_chat(chat):
    for m in chat:
        print(f"{color_role(m['role'])}: {m['content']}")

print_chat(chat)

if len(chat) == 0:
    active_role = "system"
elif chat[-1]["role"] == "user":
    active_role = "assistant"
else:
    active_role = "user"

while True:
    if active_role == 'user':
        user_input = input(color_role('user: '))
        if user_input == 'exit':
            while not chat_name or (chat_dir / chat_name).exists() or chat_name == '':
                chat_name = input('Name chat: ')
                if chat_name == 'exit':
                    exit(0)
                time.sleep(0.1)
            with (chat_dir / chat_name).open("w") as f:
                print('yoyo', chat)
                json.dump(chat, f)
            exit(0)
        if user_input in ['regenerate', 'regen']:
            chat = chat[:-1]
            active_role = 'assistant'
            print('\n\n')
            print_chat(chat)
            continue
        chat.append({"role": "user", "content": user_input})
        active_role = 'assistant'
    elif active_role == 'assistant':
        response = openai.ChatCompletion.create(
            model=model,
            messages=chat,
            stream = True,
        )
        complete_response = []
        print(color_role(f'{assistant_name}: '), end='', flush=True)
        for chunk in response:
            try:
                c = chunk.choices[0].delta.content
                print(c, end='', flush=True)
                complete_response.append(c)
            except AttributeError as e:
                pass
        print()
        complete_response = ''.join(complete_response)
        chat.append({"role": "assistant", "content": complete_response})
        active_role = 'user'