import json
import gpt_ui

test_chat_1 = [
    {
        "role": "system",
        "model": "gpt-4",
        "user": "Johannes",
        "date": "2023-05-13_00-56-13-186209",
        "content": "You are a helpful assistant, that answers every question."
    },
    {
        "role": "user",
        "model": "gpt-4",
        "user": "Johannes",
        "date": "2023-05-13_00-56-13-186560",
        "content": "hello"
    },
    {
        "role": "assistant",
        "model": "gpt-4",
        "user": "Johannes",
        "date": "2023-05-13_00-56-13-186698",
        "content": "Hello! How can"
    },
    {
        "role": "user",
        "model": "gpt-4",
        "user": "Johannes",
        "date": "2023-05-13_00-56-03-135276",
        "content": ""
    },
    {
        "role": "assistant",
        "model": "gpt-4",
        "user": "Johannes",
        "date": "2023-05-13_00-56-10-757138",
        "content": "I help you today? If you have any questions, feel free to ask."
    }
]

def test_backup_chat():
    chat_path = gpt_ui.chat_dir / "test_chat_1.json"
    gpt_ui.backup_chat(test_chat_1, chat_path)
    with chat_path.open() as f:
        assert json.load(f) == test_chat_1