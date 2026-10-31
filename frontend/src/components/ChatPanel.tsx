"use client";

import { useEffect, useRef, useState } from "react";
import { api, type ChatMessage, type ChatReply } from "@/lib/api";

interface Props {
  caseId: string;
  ownerName: string;
  initial: ChatMessage[];
  suggestions?: string[]; // one-tap merchant replies for the demo
  onReply?: (r: ChatReply) => void; // the backend may have changed the case (proposal, escalation): reload it
}

const INTENT_LABEL: Record<string, string> = {
  confirmed_issue: "Merchant confirmed the issue",
  denied_issue: "Merchant says all is fine",
  fixed: "Fixed by guided steps",
  not_fixed: "Guided fix did not work",
  asks_waiver: "Asked for money/offer → sent to a human",
  opt_out: "Merchant opted out",
};

export default function ChatPanel({ caseId, ownerName, initial, suggestions = [], onReply }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>(initial);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);
  const thread = useRef<HTMLDivElement>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const audioUrls = useRef(new Map<string, string>()); // replays don't refetch
  const [playing, setPlaying] = useState<number | null>(null);
  const playingRef = useRef<number | null>(null); // same as `playing`, but readable inside async code

  // Stop the voice when switching cases or leaving the page
  useEffect(() => () => {
    audio.current?.pause();
    audio.current = null;
  }, [caseId]);

  // When the backend sends a fresh chat (new case or after a refresh), show it: adjusted during render, not in an effect
  const [shownInitial, setShownInitial] = useState(initial);
  if (initial !== shownInitial) {
    setShownInitial(initial);
    setMessages(initial);
  }
  // Scroll only the chat box, never the whole page
  useEffect(() => {
    thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    setError("");
    setInput("");
    setMessages((m) => [...m, { role: "merchant", text }]);
    setBusy(true);
    try {
      const r = await api.chat(caseId, text);
      setMessages((m) => [...m, { role: "assistant", text: r.reply, intent: r.intent }]);
      onReply?.(r);
    } catch (e) {
      setError(`Agent unavailable: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  function stopVoice() {
    audio.current?.pause();
    audio.current = null;
    playingRef.current = null;
    setPlaying(null);
  }

  // One voice at a time: clicking the playing message stops it, clicking another switches to it
  async function speak(index: number, text: string) {
    setError("");
    const same = playing === index;
    stopVoice();
    if (same) return;
    playingRef.current = index;
    setPlaying(index);
    try {
      let url = audioUrls.current.get(text);
      if (!url) {
        url = URL.createObjectURL(await api.tts(text));
        audioUrls.current.set(text, url);
      }
      if (playingRef.current !== index) return; // stopped or switched while the audio was loading
      const a = new Audio(url);
      a.onended = () => {
        if (audio.current === a) stopVoice();
      };
      audio.current = a;
      await a.play();
    } catch (e) {
      stopVoice();
      setError(`Voice: ${(e as Error).message}`);
    }
  }

  async function toggleMic() {
    setError("");
    if (recording) {
      recorder.current?.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      const chunks: Blob[] = [];
      rec.ondataavailable = (e) => chunks.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecording(false);
        setBusy(true);
        try {
          const text = await api.stt(new Blob(chunks, { type: "audio/webm" }));
          setBusy(false);
          if (text) await send(text);
        } catch (e) {
          setError(`Speech-to-text: ${(e as Error).message}`);
          setBusy(false);
        }
      };
      rec.start();
      recorder.current = rec;
      setRecording(true);
    } catch {
      setError("Microphone permission denied");
    }
  }

  const sent = new Set(messages.filter((m) => m.role === "merchant").map((m) => m.text));
  const unused = suggestions.filter((s) => !sent.has(s));
  const optedOut = messages.some((m) => m.intent === "opt_out");

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-line shadow-sm">
      <div className="flex items-center gap-3 bg-wa-bar px-4 py-2.5 text-white">
        <div className="grid h-9 w-9 place-items-center rounded-full bg-white/20 text-sm font-black">
          {ownerName.charAt(0)}
        </div>
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-bold">{ownerName}</p>
          <p className="text-[11px] opacity-80">
            {busy ? "Paytm AI assistant is typing…" : "WhatsApp · chatting with Paytm AI assistant"}
          </p>
        </div>
        <span className="hidden rounded-full bg-white/15 px-2 py-0.5 text-[10px] font-bold sm:inline">Hindi · English</span>
      </div>

      <div ref={thread} className="wa-wall min-h-48 flex-1 space-y-2 overflow-y-auto p-3">
        {messages.length === 0 && <p className="pt-8 text-center text-xs text-muted">No conversation yet</p>}
        {messages.map((m, i) => {
          const agent = m.role === "assistant";
          return (
            <div key={i} className={`rise flex ${agent ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm shadow-sm ${agent ? "rounded-tr-sm bg-wa" : "rounded-tl-sm bg-white"}`}>
                <p className={`mb-0.5 text-[10px] font-black ${agent ? "text-wa-bar" : "text-violet"}`}>
                  {agent ? "Paytm AI assistant" : ownerName}
                </p>
                <p className="leading-relaxed">{m.text}</p>
                <div className="mt-1 flex flex-wrap items-center justify-end gap-2">
                  {m.intent && INTENT_LABEL[m.intent] && (
                    <span className="rounded bg-navy/10 px-1.5 py-0.5 text-[10px] font-bold text-navy">{INTENT_LABEL[m.intent]}</span>
                  )}
                  {agent && (
                    <button
                      onClick={() => speak(i, m.text)}
                      className={`rounded-full px-1.5 text-xs ${playing === i ? "bg-red/10 font-bold text-red" : "text-muted hover:text-navy"}`}
                      title={playing === i ? "Stop voice" : "Play in Hindi voice"}
                      aria-label={playing === i ? "Stop voice" : "Play in Hindi voice"}
                    >
                      {playing === i ? "■ Stop" : "🔊"}
                    </button>
                  )}
                  {agent && <span className="text-[11px] font-bold text-[#34b7f1]" aria-label="Read">✓✓</span>}
                </div>
              </div>
            </div>
          );
        })}
        {busy && (
          <div className="flex justify-end">
            <div className="typing rounded-xl rounded-tr-sm bg-wa px-3 py-2.5 shadow-sm" aria-label="Agent is typing">
              <span /><span /><span />
            </div>
          </div>
        )}
      </div>

      {unused.length > 0 && !optedOut && (
        <div className="flex gap-2 overflow-x-auto border-t border-line bg-white px-2 pt-2">
          <span className="shrink-0 self-center text-[10px] font-black tracking-wider text-muted uppercase">Merchant says</span>
          {unused.map((s) => (
            <button key={s} disabled={busy} onClick={() => send(s)}
              className="shrink-0 rounded-full border border-violet/30 bg-violet/5 px-3 py-1 text-xs font-bold text-violet hover:bg-violet/10 disabled:opacity-40">
              {s}
            </button>
          ))}
        </div>
      )}
      {error && <p className="bg-red/10 px-3 py-1.5 text-xs text-red">{error}</p>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex gap-2 bg-white p-2"
      >
        <label htmlFor={`chat-input-${caseId}`} className="sr-only">Message as the merchant</label>
        <input
          id={`chat-input-${caseId}`}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type as the merchant (Hindi or English)…"
          className="min-w-0 flex-1 rounded-full bg-panel px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan"
        />
        <button
          type="button"
          onClick={toggleMic}
          className={`rounded-full px-3 text-sm font-bold ${recording ? "animate-pulse bg-red text-white" : "bg-panel hover:bg-line"}`}
          title="Speak as the merchant"
          aria-label={recording ? "Stop recording" : "Speak as the merchant"}
        >
          {recording ? "■ Stop" : "🎤"}
        </button>
        <button disabled={busy || !input.trim()} className="rounded-full bg-wa-bar px-4 text-sm font-bold text-white disabled:opacity-40">
          Send
        </button>
      </form>
    </div>
  );
}
