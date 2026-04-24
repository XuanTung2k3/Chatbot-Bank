const msgerForm = get(".msger-inputarea");
const msgerInput = get(".msger-input");
const msgerChat = get(".msger-chat");
let inputSendBtn = document.getElementsByClassName("msger-send-btn")[0];
let input = document.getElementsByClassName("msger-input")[0];

let userHash = "";
let counterFiller = 0;
let timeoutId;
let resCount = 0;
const maxRes = 15;

const API_ENDPOINT = "https://non-m-finance-137003227004.us-central1.run.app";
const DEFAULT_WELCOME_MESSAGE = "Hello and welcome. I am your financial advisor at AmazingBank.\n\nI can provide information about bank services, products, and financial questions. How can I assist you today.";

const converter = new showdown.Converter();

msgerForm.addEventListener("submit", event => {
  event.preventDefault();

  const msgText = msgerInput.value.trim();
  if (!msgText) return;

  appendMessage("right", msgText);
  clearTimeout(timeoutId);
  msgerInput.value = "";

  botResponse(msgText);
});

function ensureUserHash(forceNew = false) {
  if (forceNew || !localStorage.getItem("userHash")) {
    userHash = generateHash();
    localStorage.setItem("userHash", userHash);
  } else {
    userHash = localStorage.getItem("userHash");
  }

  return userHash;
}

function formatMessage(message) {
  let formatted = (message || "").replaceAll("\n\n", "<1>");
  formatted = formatted.replaceAll("\n", "<br>");
  formatted = formatted.replaceAll("<1>", "\n\n");
  formatted = converter.makeHtml(formatted);

  if (formatted.includes("<br>*")) {
    formatted = formatted.replaceAll("<li>", "<li>*");
  }

  return formatted;
}

function setWelcomeMessage(message) {
  const welcomeText = document.getElementById("welcome-text");
  if (!welcomeText) return;

  welcomeText.innerHTML = formatMessage(message || DEFAULT_WELCOME_MESSAGE);
}

function appendMessage(side, message) {
  ensureUserHash();

  const formattedMessage = formatMessage(message);
  let msgHTML = "";

  if (side === "left") {
    msgHTML = `
      <div class="msg ${side}-msg">
        <div class="avatar-container">
          <svg class="avatar" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="48" fill="#1a5276"/>
            <circle cx="50" cy="35" r="18" fill="#f5d5c8"/>
            <path d="M32 30 Q35 15 50 15 Q65 15 68 30 Q68 25 65 22 Q60 18 50 18 Q40 18 35 22 Q32 25 32 30" fill="#3d3d3d"/>
            <circle cx="43" cy="33" r="2.5" fill="#2c3e50"/>
            <circle cx="57" cy="33" r="2.5" fill="#2c3e50"/>
            <path d="M39 28 Q43 26 47 28" stroke="#3d3d3d" stroke-width="1.5" fill="none"/>
            <path d="M53 28 Q57 26 61 28" stroke="#3d3d3d" stroke-width="1.5" fill="none"/>
            <path d="M50 35 L50 40 L47 42" stroke="#d4a58c" stroke-width="1.5" fill="none"/>
            <path d="M44 45 Q50 50 56 45" stroke="#c0392b" stroke-width="2" fill="none"/>
            <path d="M25 95 L25 65 Q25 55 50 55 Q75 55 75 65 L75 95" fill="#2c3e50"/>
            <path d="M42 55 L50 70 L58 55" fill="white"/>
            <path d="M48 55 L50 75 L52 55" fill="#c0392b"/>
            <polygon points="47,58 50,65 53,58" fill="#c0392b"/>
          </svg>
        </div>
        <div class="msg-bubble">
          <div class="msg-text">${formattedMessage}</div>
        </div>
      </div>
    `;
  } else {
    msgHTML = `
      <div class="msg ${side}-msg">
        <div class="msg-bubble">
          <div class="msg-text">${formattedMessage}</div>
        </div>
      </div>
    `;
  }

  msgerChat.insertAdjacentHTML("beforeend", msgHTML);
  msgerChat.scrollTop = msgerChat.scrollHeight;
}

function setInputState(disabled) {
  input.placeholder = disabled ? "..." : "Type your question...";
  inputSendBtn.style.cursor = disabled ? "not-allowed" : "default";
  input.style.cursor = disabled ? "not-allowed" : "default";
  inputSendBtn.disabled = disabled;
  input.disabled = disabled;
}

function addLoader() {
  const loader = `
    <div class="msg left-msg" id="msgLoader">
      <span class="loader"></span>
    </div>
  `;

  msgerChat.insertAdjacentHTML("beforeend", loader);
  msgerChat.scrollTop = msgerChat.scrollHeight;
}

function removeLoader() {
  const loader = document.getElementById("msgLoader");
  if (loader) {
    loader.remove();
  }
}

async function sendRequest(payload) {
  ensureUserHash();

  const response = await fetch(API_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return await response.json();
}

async function initializeConversation(forceNew = false) {
  ensureUserHash(forceNew);
  setWelcomeMessage(DEFAULT_WELCOME_MESSAGE);

  try {
    const data = await sendRequest({
      userHash,
      question: "",
      initConversation: true,
    });

    if (data.userHash) {
      userHash = data.userHash;
      localStorage.setItem("userHash", userHash);
    }

    setWelcomeMessage(data.response || DEFAULT_WELCOME_MESSAGE);
  } catch (error) {
    console.error(error);
    setWelcomeMessage(DEFAULT_WELCOME_MESSAGE);
  }
}

async function botResponse(msgText) {
  try {
    setInputState(true);
    addLoader();

    const data = await sendRequest({ userHash, question: msgText });

    removeLoader();
    setInputState(false);

    if (data.error) {
      appendMessage("left", "An error occurred: " + data.error);
      return;
    }

    if (data.userHash) {
      userHash = data.userHash;
      localStorage.setItem("userHash", userHash);
    }

    appendMessage("left", data.response || "No response was returned. Please resend your AmazingBank question.");
    resCount += 1;
    timeoutId = setTimeout(fillerQuestion, 300000);

    if (resCount >= maxRes) {
      const endMessage = `Session complete. Your session code is: ${userHash}.\n\nReturn anytime for additional assistance.`;
      appendMessage("left", endMessage);
      setInputState(true);
    }
  } catch (error) {
    console.error(error);
    removeLoader();
    setInputState(false);
    appendMessage("left", "I cannot connect to the server right now.");
  }
}

async function refreshChat(refreshButton) {
  if (refreshButton && refreshButton.children[0]) {
    refreshButton.children[0].style.transform = "rotate(-180deg)";
  }

  const messages = document.querySelectorAll(".left-msg, .right-msg");
  messages.forEach(message => {
    if (message.id === "welcome-msg") {
      message.style.display = "flex";
    } else {
      message.remove();
    }
  });

  counterFiller = 0;
  resCount = 0;
  await initializeConversation(true);

  if (refreshButton && refreshButton.children[0]) {
    refreshButton.children[0].style.transform = "rotate(180deg)";
  }

  setInputState(false);
}

function generateHash() {
  const crypto = window.crypto || window.msCrypto;
  const randomData = crypto.getRandomValues(new Uint32Array(2));
  return Array.from(randomData, byte => byte.toString(16).padStart(2, "0")).join("");
}

function get(selector, root = document) {
  return root.querySelector(selector);
}

function formatDate(date) {
  const h = "0" + date.getHours();
  const m = "0" + date.getMinutes();

  return `${h.slice(-2)}:${m.slice(-2)}`;
}

function openChat() {
  document.getElementById("chatbox").style.display = "flex";
}

function closeChat() {
  document.getElementById("chatbox").style.display = "none";
}

function fillerQuestion() {
  appendMessage("left", "I am still available. Send your next question when ready.");
  counterFiller = 1;
}

document.addEventListener("DOMContentLoaded", () => {
  openChat();
  setWelcomeMessage(DEFAULT_WELCOME_MESSAGE);
  initializeConversation(true);
});

console.log(API_ENDPOINT);
