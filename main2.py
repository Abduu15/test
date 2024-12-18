from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import azure.cognitiveservices.speech as speechsdk
import openai
import asyncio

# App-Instanz erstellen
app = FastAPI()

# Azure Speech Service Konfiguration
speech_key = "CiOBuQvHHEyuwnnbfejgC8rHwB8PW2JFlFBnhNogeBRxPW6nNMm6JQQJ99ALAC5RqLJXJ3w3AAAAACOGZrun"
service_region = "westeurope"
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)

# Azure OpenAI Service Konfiguration
openai.api_type = "azure"
openai.api_key = "KTcOhdHbBOr1yj67i0kGatztOPoHYu31sqOg1PQo9cb0c0l0UZP7JQQJ99ALAC5RqLJXJ3w3AAABACOGJovl"
openai.api_base = "https://openai-test428.openai.azure.com/"
openai.api_version = "2023-03-15-preview"

# Route für die Startseite (HTML-Response direkt eingebettet)
@app.get("/", response_class=HTMLResponse)
async def read_root():
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Speech-to-Speech Chatbot</title>
        <script>
            let socket;

            // Funktion zum Abspielen eines Tons
            function playStartSound() {
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const oscillator = audioCtx.createOscillator();
                oscillator.type = "sine";
                oscillator.frequency.setValueAtTime(440, audioCtx.currentTime); // A4-Ton
                oscillator.connect(audioCtx.destination);
                oscillator.start();
                oscillator.stop(audioCtx.currentTime + 0.2);
            }

            // Starten des Recordings
            function startRecording() {
                playStartSound(); // Spiele den Ton ab
                const output = document.getElementById("output");
                //output.innerHTML = "Recording started...";

                // WebSocket-Verbindung aufbauen
                socket = new WebSocket("ws://127.0.0.1:8000/ws/recording");

                // Nachrichten vom Server empfangen
                socket.onmessage = function (event) {
                    const message = event.data;
                    output.innerHTML += "<br>" + message;

                    if (message.includes("Recording stopped.")) {
                        socket.close();
                    }
                };

                // Fehlerbehandlung
                //socket.onerror = function (error) {
                //    console.error("WebSocket Error: ", error);
                //    output.innerHTML += "<br>Error occurred. Check console.";
                //};
            }
        </script>
    </head>
    <body>
        <h1>Speech-to-Speech Chatbot</h1>
        <button onclick="startRecording()">Start Recording</button>
        <div id="output" style="margin-top: 20px; font-size: 1.2em;"></div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Anfrage an Azure OpenAI senden
async def query_azure_openai(prompt: str):
    try:
        response = openai.ChatCompletion.create(
            engine="gpt-35-turbo",  # Deployment-Name von Azure
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response['choices'][0]['message']['content'].strip()
        return reply
    except Exception as e:
        print(f"Error calling Azure OpenAI: {e}")
        return "Error: Unable to get a response from Azure OpenAI."


# WebSocket-Endpunkt für Spracherkennung
@app.websocket("/ws/recording")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        # Spracherkennung vorbereiten
        speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config)

        # Einmalige Nachricht, dass die Aufnahme startet
        await websocket.send_text("Recording started...")
        await websocket.send_text("")

        while True:
            # Spracherkennung starten
            result = speech_recognizer.recognize_once()

            # Überprüfen, ob die Aufnahme erfolgreich war
            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                text = result.text
                await websocket.send_text(f"Recognized: {text}")
                await websocket.send_text("")

                # Stoppen, wenn 'Stop recording' gesagt wird
                if "stop recording" in text.lower():
                    await websocket.send_text("Recording stopped.")
                    await websocket.send_text("")
                    break

                # Anfrage an Azure OpenAI senden
                ai_response = await query_azure_openai(text)
                await websocket.send_text(f"Azure OpenAI Response: {ai_response}")
                await websocket.send_text("")

                # Text-to-Speech Antwort erzeugen und zurücksenden
                synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)

                # Warte bis die Sprachausgabe beendet ist, bevor wir weitermachen
                result = synthesizer.speak_text_async(ai_response).get()  # .get() blockiert bis zur Beendigung

                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    print(f"Speech synthesis completed for: {ai_response}")
                    await websocket.send_text("Please say something or stop recording.")
                    await websocket.send_text("")
                else:
                    await websocket.send_text("There was an error during speech synthesis.")

            elif result.reason == speechsdk.ResultReason.NoMatch:
                await websocket.send_text("No speech recognized. Try again.")
                await websocket.send_text("")
            elif result.reason == speechsdk.ResultReason.Canceled:
                await websocket.send_text("Speech recognition canceled.")
                break

    except WebSocketDisconnect:
        print("WebSocket disconnected.")
