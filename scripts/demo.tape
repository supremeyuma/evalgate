# EvalGate demo tape. Record with: vhs scripts/demo.tape
# The resulting GIF is docs/demo.gif. Recording is a human step.
Output docs/demo.gif

Set Shell "powershell"
Set FontSize 15
Set Width 1200
Set Height 720
Set Padding 20
Set TypingSpeed 35ms

Type "uv run evalgate validate examples/support/suite.yaml"
Enter
Sleep 2s

Type "uv run evalgate run examples/support/suite.yaml --mock --json reports/demo.json"
Enter
Sleep 4s

Type "uv run evalgate run examples/support/suite.yaml --mock --prompt-variant weakened --baseline reports/demo.json --json reports/weak.json"
Enter
Sleep 5s

Type "uv run evalgate comment --report reports/weak.json --baseline reports/demo.json"
Enter
Sleep 4s
