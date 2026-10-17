$e = @{}; Get-Content .env | Where-Object { $_ -match '^[A-Z_0-9]+=' } | ForEach-Object { $k,$v = $_ -split '=',2; $e[$k] = $v.Trim() }
$pw = $e.DEMO_PASSWORD
$base = "http://127.0.0.1:8011"
New-Item -ItemType Directory -Force .local | Out-Null
$py = (Get-Command python).Source
$srv = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","app.main:app","--port","8011" -WorkingDirectory "$PWD\backend" -PassThru -WindowStyle Hidden -RedirectStandardOutput "$PWD\.local\server.out" -RedirectStandardError "$PWD\.local\server.err"
Start-Sleep 5

function Call($method, $url, $token, $body) {
  $h = @{}
  if ($token) { $h["Authorization"] = "Bearer $token" }
  try {
    if ($body) { $r = Invoke-WebRequest -UseBasicParsing -Method $method -Uri $url -Headers $h -ContentType "application/json" -Body ($body | ConvertTo-Json) }
    else { $r = Invoke-WebRequest -UseBasicParsing -Method $method -Uri $url -Headers $h }
    return [pscustomobject]@{ Status = [int]$r.StatusCode; Body = $r.Content }
  } catch {
    $resp = $_.Exception.Response
    $code = 0; $txt = ""
    if ($resp) { $code = [int]$resp.StatusCode; try { $txt = (New-Object IO.StreamReader($resp.GetResponseStream())).ReadToEnd() } catch {} }
    return [pscustomobject]@{ Status = $code; Body = $txt }
  }
}
function Check($label, $got, $want) { "{0,-46} got {1,-5} want {2,-5} {3}" -f $label, $got, $want, $(if ($got -eq $want) {"PASS"} else {"FAIL"}) }

try {
  $health = Call GET "$base/health" $null $null
  if ($health.Status -ne 200) { "server did not start:"; Get-Content "$PWD\.local\server.err" -Tail 15; return }
  $paths = (Invoke-RestMethod "$base/openapi.json").paths.PSObject.Properties.Name
  "paths: " + ($paths -join ", ")
  $coll = $paths | Where-Object { $_ -match '^/[^{}]*shipments/?$' } | Select-Object -First 1
  $item = $paths | Where-Object { $_ -match '^/[^{}]*shipments/\{[^}]+\}/?$' } | Select-Object -First 1
  if (-not $coll -or -not $item) { "could not find the shipment paths above, stopping"; return }

  $tok = @{}
  foreach ($u in "importer","agent","reviewer") {
    $r = Call POST "$base/auth/login" $null @{ email = "${u}@demo.test"; password = $pw }
    $tok[$u] = if ($r.Status -eq 200) { ($r.Body | ConvertFrom-Json).access_token } else { $null }
    Check "login as $u" $r.Status 200
  }
  $a = Call POST "$base/auth/login" $null @{ email = "importer@demo.test"; password = "wrong-password-123" }
  $b = Call POST "$base/auth/login" $null @{ email = "nobody@demo.test"; password = "wrong-password-123" }
  Check "wrong password" $a.Status 401
  Check "unknown email" $b.Status 401
  Check "same error text for both" ($a.Body -eq $b.Body) $true

  $c = Call POST "$base$coll" $tok.importer @{ reference = "AUTHTEST-" + (Get-Random -Maximum 99999) }
  Check "importer creates a shipment" ($c.Status -in 200,201) $true
  $id = ($c.Body | ConvertFrom-Json).id
  if (-not $id) { "create answered: " + $c.Body; return }

  $url = $base + ($item -replace '\{[^}]+\}', $id)
  $p = $tok.importer.Split('.'); $bad = $p[0] + "." + $p[1] + "." + ("A" * $p[2].Length)
  Check "owner reads own shipment" (Call GET $url $tok.importer).Status 200
  Check "agent, not assigned -> 404" (Call GET $url $tok.agent).Status 404
  Check "reviewer reads it" (Call GET $url $tok.reviewer).Status 200
  Check "nonexistent id -> 404" (Call GET ($base + ($item -replace '\{[^}]+\}', [guid]::NewGuid().ToString())) $tok.importer).Status 404
  Check "agent's list hides it" ((Call GET "$base$coll" $tok.agent).Body -notmatch $id) $true
  Check "reviewer creating -> 403" (Call POST "$base$coll" $tok.reviewer @{ reference = "AUTHTEST-R" }).Status 403
  Check "tampered token -> 401" (Call GET $url $bad).Status 401
  Check "no token -> 401" (Call GET $url $null).Status 401
} finally {
  Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
}