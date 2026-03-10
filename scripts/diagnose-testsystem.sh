#!/bin/bash
# Diagnose: Warum liefert das Testsystem 500?
# Auf dem Server: sudo bash /opt/terminmarktplatz-test/scripts/diagnose-testsystem.sh

echo "=== Testsystem-Diagnose ==="
echo ""

echo "1. healthz (DB-Verbindung):"
curl -s http://127.0.0.1:8001/healthz | python3 -m json.tool 2>/dev/null || curl -s http://127.0.0.1:8001/healthz
echo ""
echo ""

echo "2. public/slots (erste 500 Zeichen):"
curl -s -w "\nHTTP-Status: %{http_code}" "http://127.0.0.1:8001/public/slots?include_full=1" | head -c 600
echo ""
echo ""
echo ""

echo "3. Nginx: Welcher Port für test.terminmarktplatz.de?"
grep -A2 "server_name test.terminmarktplatz" /etc/nginx/sites-enabled/* 2>/dev/null | grep -E "proxy_pass|server_name" || grep -A2 "test.terminmarktplatz" /etc/nginx/sites-available/* 2>/dev/null | head -10
echo ""

echo "4. Letzte Service-Fehler:"
journalctl -u terminmarktplatz-test -n 20 --no-pager 2>/dev/null | tail -25
echo ""
echo "=== Ende ==="
