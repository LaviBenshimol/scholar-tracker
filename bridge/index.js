/**
 * Scholar Tracker — WhatsApp Web Bridge (Baileys)
 *
 * Connects to WhatsApp via QR code scan (like WhatsApp Web / OpenClaw).
 * Forwards incoming messages to the FastAPI backend and relays the reply.
 *
 * Usage:
 *   cd bridge && npm install && npm start
 *
 * On first run a QR code appears in your terminal — scan it with
 * WhatsApp → Settings → Linked Devices → Link a Device.
 * The session is saved locally (auth_info/) so you won't need to scan again.
 */

// Prevent crashes from unhandled errors
process.on("uncaughtException", (err) => {
  console.error("⚠️  Uncaught error (bridge stays alive):", err.message);
});
process.on("unhandledRejection", (err) => {
  console.error("⚠️  Unhandled rejection (bridge stays alive):", err?.message || err);
});

const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} = require("baileys");
const http = require("http");
const qrcodeTerminal = require("qrcode-terminal");

// ── Config ───────────────────────────────────────────────────
const BACKEND_URL = "http://localhost:8000/ui-api/chat";
const OWNER_NUMBER = process.env.OWNER_NUMBER || "";

// Empty = allow ALL senders.  Set comma-separated list to restrict.
const ALLOWED_NUMBERS = (process.env.ALLOWED_PHONE_NUMBERS || "")
  .split(",")
  .map((n) => n.trim())
  .filter(Boolean);

// ─────────────────────────────────────────────────────────────

async function startBridge() {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger: {               // suppress noisy Baileys internal logs
      level: "silent",
      info: () => {},
      debug: () => {},
      warn: () => {},
      error: () => {},
      trace: () => {},
      child: () => ({ info: () => {}, debug: () => {}, warn: () => {}, error: () => {}, trace: () => {}, child: () => ({}) }),
    },
  });

  // ── QR Code ──────────────────────────────────────────────
  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      console.log("\n📱 Scan this QR code with WhatsApp:\n");
      qrcodeTerminal.generate(qr, { small: true });
      console.log("\n   WhatsApp → Settings → Linked Devices → Link a Device\n");
    }

    if (connection === "close") {
      const statusCode =
        lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      console.log(
        `🔴 Connection closed (code ${statusCode}). ${
          shouldReconnect ? "Reconnecting..." : "Logged out — delete auth_info/ and restart."
        }`
      );

      if (shouldReconnect) {
        console.log("   Reconnecting in 3 seconds...");
        setTimeout(startBridge, 3000);
      }
    }

    if (connection === "open") {
      console.log("🟢 WhatsApp bridge is READY!");
      console.log(`   Owner: ${OWNER_NUMBER}`);
      console.log(`   Backend: ${BACKEND_URL}`);
      console.log(
        `   Allowed senders: ${
          ALLOWED_NUMBERS.length > 0
            ? ALLOWED_NUMBERS.join(", ")
            : "ALL (no whitelist)"
        }\n`
      );
    }
  });

  // Save credentials whenever they update
  sock.ev.on("creds.update", saveCreds);

  // ── Incoming Messages ────────────────────────────────────
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (msg.key.fromMe) continue;
      if (msg.key.remoteJid.endsWith("@g.us")) continue;

      const sender = msg.key.remoteJid.replace("@s.whatsapp.net", "");

      const text =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        "";
      if (!text.trim()) continue;

      // Sender whitelist (empty = allow all)
      if (ALLOWED_NUMBERS.length > 0 && !ALLOWED_NUMBERS.includes(sender)) {
        console.log(`🚫 Ignored message from: ${sender}`);
        continue;
      }

      console.log(`📩 ${sender}: ${text}`);

      try {
        const reply = await forwardToBackend(text.trim());
        if (reply.type === "image") {
          // Download image and send via Baileys
          const https = require("https");
          const imgBuf = await new Promise((resolve, reject) => {
            https.get(reply.url, (res) => {
              // Follow redirects
              if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
                https.get(res.headers.location, (res2) => {
                  const chunks = [];
                  res2.on("data", (c) => chunks.push(c));
                  res2.on("end", () => resolve(Buffer.concat(chunks)));
                  res2.on("error", reject);
                }).on("error", reject);
                return;
              }
              const chunks = [];
              res.on("data", (c) => chunks.push(c));
              res.on("end", () => resolve(Buffer.concat(chunks)));
              res.on("error", reject);
            }).on("error", reject);
          });
          await sock.sendMessage(msg.key.remoteJid, {
            image: imgBuf,
            caption: reply.caption || "",
          });
          console.log(`\uD83D\uDCF8 Bot: [image] ${reply.caption.substring(0, 60)}`);
        } else {
          await sock.sendMessage(msg.key.remoteJid, { text: reply.text });
          console.log(`\uD83D\uDCE4 Bot: ${reply.text.substring(0, 80)}...`);
        }
      } catch (err) {
        console.error("\u274C Backend error:", err.message);
        await sock.sendMessage(msg.key.remoteJid, {
          text: "\u26A0\uFE0F Sorry, the tracker backend is not responding.",
        });
      }
    }
  });
}

// ── Number-to-intent mapping ───────────────────────────────
// Hardcoded so numbers always work, even after bridge restart
const MENU_OPTIONS = {
  1: "get_stats",
  2: "get_meme",
  3: "help",
};

function resolveNumberInput(text) {
  const num = parseInt(text);
  if (!isNaN(num) && MENU_OPTIONS[num]) {
    return MENU_OPTIONS[num];
  }
  return text;
}

// ── Forward to FastAPI ─────────────────────────────────────
// Returns: { type: "text", text: "..." }
//      or: { type: "image", url: "...", caption: "..." }
function forwardToBackend(text) {
  // Map numbered replies to actual intents
  text = resolveNumberInput(text);

  return new Promise((resolve, reject) => {
    const payload = JSON.stringify({
      type: "text",
      text: { body: text },
    });

    const url = new URL(BACKEND_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(payload),
      },
    };

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          const json = JSON.parse(data);
          if (json.type === "text") {
            resolve({ type: "text", text: json.text.body });
          } else if (json.type === "image") {
            resolve({
              type: "image",
              url: json.image.url,
              caption: json.image.caption || "",
            });
          } else if (json.type === "interactive") {
            // Format interactive menu as clean text
            const header = json.interactive.header?.text || "";
            const body = json.interactive.body?.text || "";
            const buttons = json.interactive.action?.buttons || [];

            // Update dynamic mappings from response
            buttons.forEach((b, i) => {
              MENU_OPTIONS[i + 1] = b.reply.id;
            });

            const buttonLines = buttons
              .map((b, i) => `  ${i + 1}. ${b.title || b.reply.id}`)
              .join("\n");

            const parts = [];
            if (header) parts.push(`*${header}*`);
            if (body) parts.push(body);
            parts.push("");
            parts.push(buttonLines);
            parts.push("");
            parts.push("Reply with a number to choose.");

            resolve({ type: "text", text: parts.join("\n") });
          } else {
            resolve({ type: "text", text: JSON.stringify(json) });
          }
        } catch (e) {
          reject(new Error("Invalid JSON from backend"));
        }
      });
    });

    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

// ── Graceful shutdown ──────────────────────────────────────
process.on("SIGINT", () => {
  console.log("\n🔴 Shutting down bridge...");
  process.exit(0);
});

// ── Start ──────────────────────────────────────────────────
console.log("🚀 Starting WhatsApp Web bridge (Baileys)...\n");
startBridge();
