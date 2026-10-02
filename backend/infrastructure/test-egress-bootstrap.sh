#!/bin/bash
set -euo pipefail
umask 077
# Dedicated NAT host; no application data or credentials on this machine.
# A small encrypted-disk swapfile prevents package installation exhausting instance RAM.
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
fi
swapon /swapfile || swapon --show | grep -q /swapfile
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
# EIP association is a separate CloudFormation resource and can arrive after boot.
for attempt in $(seq 1 30); do
  if dnf install -y nftables; then break; fi
  sleep 10
done
command -v nft
cat > /etc/sysctl.d/90-fitfinity-nat.conf <<'EOF'
# Start closed; only the firewall service enables forwarding.
net.ipv4.ip_forward=0
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF
cat > /usr/local/sbin/fitfinity-nat-start <<'EOF'
#!/bin/bash
set -euo pipefail
sysctl -w net.ipv4.ip_forward=0
uplink=$(ip -4 route show default | awk 'NR==1 {print $5}')
[[ "$uplink" =~ ^[a-zA-Z0-9_-]+$ ]]
if nft list table ip fitfinity_nat >/dev/null 2>&1; then
  nft delete table ip fitfinity_nat
fi
nft -f - <<RULES
table ip fitfinity_nat {
  chain forward {
    type filter hook forward priority 0; policy drop;
    ct state invalid drop
    ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4, 240.0.0.0/4 } ct state new drop
    iifname "$uplink" oifname "$uplink" ip daddr 10.84.32.0/23 ct state established,related accept
    iifname "$uplink" oifname "$uplink" ip saddr 10.84.32.0/23 tcp dport 443 ct state new,established accept
  }
  chain postrouting {
    type nat hook postrouting priority 100; policy accept;
    oifname "$uplink" ip saddr 10.84.32.0/23 tcp dport 443 masquerade
  }
}
RULES
sysctl -w net.ipv4.conf.all.rp_filter=0 net.ipv4.conf.default.rp_filter=0
sysctl -w net.ipv4.ip_forward=1
EOF
chmod 700 /usr/local/sbin/fitfinity-nat-start
cat > /etc/systemd/system/fitfinity-nat.service <<'EOF'
[Unit]
Description=Fitfinity private-subnet HTTPS NAT
Wants=network-online.target
After=network-online.target systemd-sysctl.service
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/fitfinity-nat-start
ExecStop=/usr/sbin/sysctl -w net.ipv4.ip_forward=0
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now fitfinity-nat.service
systemctl enable --now amazon-ssm-agent
systemctl is-active --quiet fitfinity-nat.service
nft list table ip fitfinity_nat > /var/lib/fitfinity-nat-rules-at-bootstrap.txt
date -u +%FT%TZ > /var/lib/fitfinity-nat-ready
