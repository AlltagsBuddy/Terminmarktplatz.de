# Manueller Test: Webhook an WWS senden (wie Terminmarktplatz es macht)
# Aufruf: .\scripts\test-webhook-manual.ps1 -WebhookUrl "https://DEINE-NGROK-URL.ngrok-free.app/api/v1/appointments" -ApiKey "DEIN-API-SCHLÜSSEL"

param(
    [Parameter(Mandatory=$true)]
    [string]$WebhookUrl,
    [Parameter(Mandatory=$true)]
    [string]$ApiKey
)

$payload = @{
    external_booking_id = "tm-test-12345"
    action = "booking"
    starts_at = "2026-03-25T10:00:00+0100"
    ends_at = "2026-03-25T11:00:00+0100"
    title = "Test-Termin von Terminmarktplatz"
    customer_first_name = "Max"
    customer_last_name = "Mustermann"
    customer_email = "test@example.com"
    customer_phone = "0123456789"
} | ConvertTo-Json

$headers = @{
    "Content-Type" = "application/json"
    "X-API-Key" = $ApiKey
    "ngrok-skip-browser-warning" = "1"
}

Write-Host "Sende Test-Webhook an: $WebhookUrl"
Write-Host "Payload: $payload"
Write-Host ""

try {
    $response = Invoke-WebRequest -Uri $WebhookUrl -Method POST -Body $payload -Headers $headers -UseBasicParsing -TimeoutSec 10
    Write-Host "Erfolg! Status: $($response.StatusCode)"
    Write-Host "Antwort: $($response.Content)"
} catch {
    Write-Host "Fehler: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $reader.BaseStream.Position = 0
        Write-Host "Antwort-Body: $($reader.ReadToEnd())"
    }
}
