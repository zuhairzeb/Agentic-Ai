import gradio as gr
import subprocess
import threading
import os

def run_chainlit():
    subprocess.run(["chainlit", "run", "app.py", "--host=0.0.0.0", "--port=7860"])

threading.Thread(target=run_chainlit).start()

def placeholder():
    return "Chainlit is running on port 7860. Please wait a moment..."

demo = gr.Interface(fn=placeholder, inputs=[], outputs="text")
demo.launch()
