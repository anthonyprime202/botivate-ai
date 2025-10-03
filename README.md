# Botivate AI

This README provides a comprehensive guide to understanding, deploying, and using the Botivate AI project. It's a powerful conversational agent that connects your Google Sheets data to an intelligent chatbot.



***

### **Project Overview**

Botivate AI is a conversational AI agent that can interact with users and query a SQLite database. It is designed to be integrated with Google Sheets, allowing the agent to access and process data stored in a spreadsheet in real-time. The project consists of a frontend chat interface, a Python backend powered by FastAPI and LangChain, and a Google Apps Script to synchronize data from a Google Sheet to the backend.

***

### **How It Works**

The application is composed of several key components that work together in a seamless workflow:

* **Frontend**: A simple HTML file (`index.html`) with JavaScript that creates a user-friendly chat interface in the browser. It communicates with the backend via HTTP requests.
* **Backend**: A Python application built with FastAPI (`main.py`). It exposes a `/chat` endpoint to handle user messages and a `/webhook/sync` endpoint to receive data from the Google Apps Script.
* **Agent**: The core logic of the chatbot, built with LangChain and LangGraph (`agent.py`). The agent can classify user intent, handle general conversation, and dynamically generate and execute SQL queries against a database based on the user's questions.
* **Database Sync**: A Python script (`script.py`) that fetches data from a Google Apps Script URL and writes it to a local SQLite database (`sheets.db`). This script is triggered by a webhook from the Google Apps Script, ensuring the data is always up-to-date.
* **Google Apps Script**: A script that runs on a Google Sheet. It exposes the sheet data as a JSON endpoint and calls the backend's webhook whenever the sheet is edited.



***

### **Deployment Guide**

To deploy the Botivate AI project, follow these steps to set up the backend, the Google Apps Script, and the frontend.

#### **1. Backend Setup**

First, you'll need to set up the Python backend on your local machine or a server.

1.  **Clone the Repository**: If the project is in a Git repository, clone it to your local machine. Otherwise, ensure you have all the project files in a single directory.
2.  **Create a Virtual Environment**: It's highly recommended to use a virtual environment to manage project dependencies and avoid conflicts.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```
3.  **Install Dependencies**: Install the required Python packages using the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configure Environment Variables**: Create a `.env` file in the project's root directory. This file will store your secret keys and other configuration variables. You can copy the `.env.example` file to get started. Your `.env` file should look like this:
    ```env
    APPS_SCRIPT_URL="<YOUR_GOOGLE_APPS_SCRIPT_URL>"
    OPENAI_API_KEY="<YOUR_OPENAI_API_KEY>"
    WEBHOOK_SECRET="<A_STRONG_SECRET_PHRASE_YOU_CREATE>"
    ```
5.  **Run the Backend Server**: Start the FastAPI server using `uvicorn`.
    ```bash
    uvicorn main:app --host 0.0.0.0 --port $PORT
    ```
    This will start the backend server, and you should see output indicating that the initial database sync is running.

#### **2. Google Apps Script Setup**

Next, you need to set up the Google Apps Script to connect your Google Sheet to the backend.

1.  **Create a Google Sheet**: Create a new Google Sheet. Add some data to it, making sure the first row contains your column headers.
2.  **Open the Apps Script Editor**: In your Google Sheet, go to **Extensions > Apps Script**.
3.  **Add the Script Code**: Copy and paste the code below into the script editor.

    **Configure the variables at the top of the script:**
    * `WEBHOOK_URL`: The URL of your backend's webhook. If you're running the backend locally, you'll need to use a tunneling service like **ngrok** to expose your local server to the internet. The URL should look something like `https://<your-ngrok-id>.ngrok.io/webhook/sync`.
    * `WEBHOOK_SECRET`: This must be the **exact same secret** you defined in your `.env` file.
    * `ALLOWED_SHEETS`: An array of strings containing the names of the sheets you want to sync with the database (e.g., `["Tasks", "Inventory"]`).

    ```javascript
    /**
     * CONFIGURATION
     * ----------------
     * UPDATE these variables with your own settings.
     */
    const WEBHOOK_URL = "YOUR_BACKEND_WEBHOOK_URL_HERE"; 
    const WEBHOOK_SECRET = "YOUR_SECRET_PHRASE_HERE";
    const ALLOWED_SHEETS = [
      "Sheet1",
      "Sheet2",
      // Add sheet names you want to sync here
    ];
    
    /**
     * 1) Publishes the data from allowed sheets as JSON.
     * This function runs when someone visits the deployment URL.
     */
    function doGet() {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const output = {};
    
      ss.getSheets().forEach(sheet => {
        const sheetName = sheet.getName();
        if (ALLOWED_SHEETS.indexOf(sheetName) === -1) return; // Skip sheets not in the allowed list
    
        const data = sheet.getDataRange().getValues();
        if (!data || data.length < 2) return; // Skip empty sheets or sheets with only headers
    
        const headers = data.shift();
        const rows = data.map(row => {
          const rowObject = {};
          headers.forEach((header, index) => (rowObject[header] = row[index]));
          return rowObject;
        });
    
        output[sheetName] = rows;
      });
    
      return ContentService.createTextOutput(JSON.stringify(output))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    
    /**
     * 2) A helper function to call the FastAPI webhook.
     */
    function callWebhook() {
      try {
        const options = {
          'method': 'post',
          'contentType': 'application/json',
          'headers': {
            'X-Webhook-Secret': WEBHOOK_SECRET
          },
          'muteHttpExceptions': true // Prevents script from stopping on HTTP errors
        };
    
        const response = UrlFetchApp.fetch(WEBHOOK_URL, options);
        Logger.log('Webhook Response:', response.getContentText());
      } catch (e) {
        Logger.log('Error calling webhook:', e.toString());
      }
    }
    
    /**
     * 3) The trigger function that runs on every edit.
     * This needs to be set up in the Triggers section of Apps Script.
     */
    function onSheetEdit(e) {
      // The 'e' object contains info about the edit, but we just need to know an edit occurred.
      Logger.log("Sheet was edited. Calling webhook to sync data...");
      callWebhook();
    }
    ```

4.  **Deploy as a Web App**:
    * Click the **Deploy** button in the Apps Script editor and select **New deployment**.
    * Choose **Web app** as the deployment type.
    * In the configuration settings, make sure to set **Execute as** to **Me** and **Who has access** to **Anyone**.
    * Click **Deploy**.
    * Authorize the script's permissions when prompted.
    * After deployment, you will be given a **Web app URL**. Copy this URL and paste it into your `.env` file as the value for `APPS_SCRIPT_URL`.

5.  **Set Up an "On Edit" Trigger**: To automatically sync data when the sheet is edited, you need to set up a trigger.
    * In the Apps Script editor, go to the **Triggers** tab (clock icon on the left).
    * Click **Add Trigger**.
    * Configure the trigger as follows:
        * **Choose which function to run**: `onSheetEdit`
        * **Choose which deployment should run**: `Head`
        * **Select event source**: `From spreadsheet`
        * **Select event type**: `On edit`
    * Click **Save**.

#### **3. Frontend Setup**

Finally, set up the frontend to interact with your chatbot.

1.  **Open `index.html`**: Open the `index.html` file in a web browser.
2.  **Update the API URL**: In the `index.html` file, find the following line of JavaScript and update the URL to point to your backend's `/chat` endpoint.
    ```javascript
    // --- CONFIGURATION ---
    const API_URL = "http://127.0.0.1:8000/chat"; // 👈 Change this to your backend URL
    ```

### **How to Use**

Once you have completed all the deployment steps, you can start using the Botivate AI agent:

* **Open the Chat Interface**: Open the `index.html` file in your browser.
* **Interact with the Agent**: Type messages into the input box and press Enter or click the send button to chat with the agent. The agent will respond based on its capabilities, which include answering general questions and querying the real-time data from your Google Sheet.

