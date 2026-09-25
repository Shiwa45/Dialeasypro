# Fonts

The app uses one family, **Plus Jakarta Sans** — the same typeface as the web
app — registered in `pubspec.yaml` as five static weights:

| File | Weight |
|---|---|
| PlusJakartaSans-Regular.ttf | 400 |
| PlusJakartaSans-Medium.ttf | 500 |
| PlusJakartaSans-SemiBold.ttf | 600 |
| PlusJakartaSans-Bold.ttf | 700 |
| PlusJakartaSans-ExtraBold.ttf | 800 |

Source: https://github.com/tokotype/PlusJakartaSans (SIL Open Font License).

To fetch them again:

```bash
cd assets/fonts
for w in Regular Medium SemiBold Bold ExtraBold; do
  curl -sSfL -o "PlusJakartaSans-$w.ttf" "https://github.com/tokotype/PlusJakartaSans/raw/master/fonts/ttf/PlusJakartaSans-$w.ttf"
done
```
