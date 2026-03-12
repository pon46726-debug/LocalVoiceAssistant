#!/usr/bin/env python3
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

def main():
    print("=" * 50)
    print("Local Voice Assistant")
    print("Loading...")
    print("=" * 50)
    
    # Проверка зависимостей
    deps = {
        "torch": "PyTorch",
        "pyaudio": "PyAudio", 
        "vosk": "Vosk",
        "customtkinter": "CustomTkinter",
        "numpy": "NumPy"
    }
    
    all_ok = True
    for module, name in deps.items():
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name}: pip install {module}")
            all_ok = False
    
    if not all_ok:
        input("\nНажми Enter для выхода...")
        return
    
    print("\n🚀 Запуск интерфейса...")
    
    from assistant.gui import AssistantGUI
    app = AssistantGUI()
    app.run()

if __name__ == "__main__":
    main()