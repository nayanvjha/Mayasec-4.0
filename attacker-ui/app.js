const statusEl = document.getElementById('status');
const logEl = document.getElementById('log');

const ingestorUrlInput = document.getElementById('ingestorUrl');
const targetIpInput = document.getElementById('targetIp');
const attackerIpInput = document.getElementById('attackerIp');
const burstCountInput = document.getElementById('burstCount');

const sshAttackBtn = document.getElementById('sshAttack');
const portScanBtn = document.getElementById('portScan');
const webLoginBtn = document.getElementById('webLogin');

const usernames = ['root', 'admin', 'ubuntu', 'test', 'guest', 'postgres'];
const ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 3306, 3389, 5432];

function log(message) {
  const line = document.createElement('div');
  line.textContent = message;
  logEl.prepend(line);
}

function setStatus(text) {
  statusEl.textContent = text;
}

async function sendAttack(action, payload) {
  const baseUrl = ingestorUrlInput.value.trim().replace(/\/$/, '');
  const url = `${baseUrl}/attack/${action}`;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || 'Request failed');
  }

  return response.json();
}

async function runBurst(action, payload) {
  setStatus('Attacking...');
  try {
    const result = await sendAttack(action, payload);
    log(`Triggered ${action}: ${JSON.stringify(result)}`);
  } catch (err) {
    log(`Error: ${err.message}`);
  }
  setStatus('Idle');
}

sshAttackBtn.addEventListener('click', async () => {
  const payload = {
    attacker_ip: attackerIpInput.value.trim(),
    target: targetIpInput.value.trim(),
    count: Number(burstCountInput.value) || 10,
  };

  await runBurst('ssh', payload);
});

portScanBtn.addEventListener('click', async () => {
  const payload = {
    attacker_ip: attackerIpInput.value.trim(),
    target: targetIpInput.value.trim(),
    count: Number(burstCountInput.value) || 10,
  };

  await runBurst('port-scan', payload);
});

webLoginBtn.addEventListener('click', async () => {
  const payload = {
    attacker_ip: attackerIpInput.value.trim(),
    target: targetIpInput.value.trim(),
    count: Number(burstCountInput.value) || 10,
  };

  await runBurst('web-login', payload);
});
