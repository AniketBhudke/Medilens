// Alarm tone generated with WebAudio (no audio file needed).
let ctx = null;
let timer = null;

export function unlockAudio() {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
  } catch { /* audio not available */ }
}

function beep() {
  if (!ctx) return;
  const t0 = ctx.currentTime;
  [0, 0.28, 0.56].forEach((off) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "square";
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.0001, t0 + off);
    gain.gain.exponentialRampToValueAtTime(0.35, t0 + off + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + off + 0.2);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0 + off);
    osc.stop(t0 + off + 0.22);
  });
  if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
}

export function startAlarm() {
  if (timer) return;
  beep();
  timer = setInterval(beep, 2000);
}

export function stopAlarm() {
  clearInterval(timer);
  timer = null;
  if (navigator.vibrate) navigator.vibrate(0);
}
