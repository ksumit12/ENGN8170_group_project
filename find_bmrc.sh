#!/usr/bin/env bash
set -euo pipefail

# Find a device named bmrc.local or bmrc on the current network.
# Tries: getent/avahi direct resolve -> mDNS browse -> ping sweep (nmap) + reverse mDNS.
# Exit codes: 0=found, 1=not found, 2=env/deps error.

NAME_CANDIDATES=("bmrc.local" "bmrc")

have() { command -v "$1" >/dev/null 2>&1; }

say() { printf "%s\n" "$*"; }
ok()  { printf "[OK] %s\n" "$*"; }
warn(){ printf "[WARN] %s\n" "$*" >&2; }
err() { printf "[ERR] %s\n" "$*" >&2; }

print_result() {
  local ip="$1" host="$2" how="$3"
  ok "Found device: host=${host} ip=${ip} (via ${how})"
  exit 0
}

# 1) Quick direct resolves (getent / avahi-resolve)
for H in "${NAME_CANDIDATES[@]}"; do
  if have getent; then
    if OUT="$(getent hosts "$H" 2>/dev/null)" && [[ -n "$OUT" ]]; then
      IP="${OUT%% *}"
      [[ -n "$IP" ]] && print_result "$IP" "$H" "getent"
    fi
  fi
  if have avahi-resolve; then
    # -n = hostname, mDNS will try .local names; try both forms
    if OUT="$(avahi-resolve -n "$H" 2>/dev/null)" && [[ -n "$OUT" ]]; then
      IP="$(awk '{print $2}' <<<"$OUT")"
      [[ -n "$IP" ]] && print_result "$IP" "$H" "avahi-resolve(name)"
    fi
  fi
done

# 2) mDNS browse for common workstation/ssh services and filter for bmrc*
BROWSERS=()
have avahi-browse && BROWSERS+=("avahi-browse")
if [[ ${#BROWSERS[@]} -gt 0 ]]; then
  SERVICES=("_workstation._tcp" "_ssh._tcp" "_sftp-ssh._tcp")
  for SVC in "${SERVICES[@]}"; do
    if OUT="$(avahi-browse -rt "$SVC" 2>/dev/null)"; then
      # Lines look like: "=;eth0;IPv4;bmrc;_workstation._tcp;local;host = bmrc.local; address = 192.168.1.23; port = 9; ..."
      LINE="$(grep -iE '(^=|host = ).*(bmrc)' <<<"$OUT" | head -n1 || true)"
      if [[ -n "$LINE" ]]; then
        HOST="$(sed -n 's/.*host = \([^;]*\).*/\1/p' <<<"$LINE")"
        IP="$(sed -n 's/.*address = \([^;]*\).*/\1/p' <<<"$LINE")"
        [[ -n "$IP" && -n "$HOST" ]] && print_result "$IP" "$HOST" "avahi-browse ${SVC}"
      fi
    fi
  done
fi

# 3) Ping sweep fallback (needs nmap); then reverse mDNS on each IP
if have nmap; then
  # Figure out the first global IPv4 subnet (e.g., 192.168.1.0/24)
  if ! have ip; then
    err "ip command not found; cannot derive subnet for scan."
    exit 2
  fi
  CIDR="$(ip -o -4 addr show scope global up | awk '{print $4}' | head -n1)"
  if [[ -z "${CIDR:-}" ]]; then
    err "Could not determine your IPv4 subnet. Are you connected to a network?"
    exit 2
  fi
  warn "Direct resolve failed; scanning ${CIDR} (ping sweep). This may take a bit…"
  # -sn = ping scan only
  MAP="$(nmap -sn "$CIDR" 2>/dev/null || true)"
  # Extract live IPs
  mapfile -t IPS < <(awk '/Nmap scan report for /{print $5}' <<<"$MAP" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')
  if [[ ${#IPS[@]} -eq 0 ]]; then
    warn "No live hosts found during scan."
  else
    for IP in "${IPS[@]}"; do
      # Try to get mDNS hostname for IP
      HOST=""
      if have avahi-resolve; then
        if OUT="$(avahi-resolve -a "$IP" 2>/dev/null)" && [[ -n "$OUT" ]]; then
          HOST="$(awk '{print $2}' <<<"$OUT")"
        fi
      fi
      # Fall back to getent (reverse DNS) if no avahi
      if [[ -z "$HOST" ]] && have getent; then
        if RDNS="$(getent hosts "$IP" 2>/dev/null)"; then
          HOST="$(awk '{print $2}' <<<"$RDNS")"
        fi
      fi
      # Check for bmrc match
      if [[ "$HOST" =~ ^bmrc(\.local)?$ ]]; then
        print_result "$IP" "$HOST" "nmap+reverse-lookup"
      fi
    done
  fi
else
  warn "nmap not found; skipping ping sweep fallback."
fi

# If we got here, nothing found.
err "No device named 'bmrc.local' or 'bmrc' was found on your current network."
warn "Notes: On some uni/enterprise Wi-Fi, mDNS (Bonjour) is blocked; direct discovery may not work."
exit 1
