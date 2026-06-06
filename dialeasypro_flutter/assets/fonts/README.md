# Fonts Setup

The app uses two Google Fonts:
- Space Grotesk (headings, buttons, labels)
- DM Sans (body text)

Both must be placed in this directory before running the app.

## Required filenames
- SpaceGrotesk-Regular.ttf, SpaceGrotesk-Medium.ttf, SpaceGrotesk-SemiBold.ttf, SpaceGrotesk-Bold.ttf
- DMSans-Regular.ttf, DMSans-Medium.ttf, DMSans-SemiBold.ttf

## One-line setup
```bash
cd assets/fonts
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Regular.ttf" -o SpaceGrotesk-Regular.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Medium.ttf" -o SpaceGrotesk-Medium.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-SemiBold.ttf" -o SpaceGrotesk-SemiBold.ttf
curl -sL "https://github.com/floriankarsten/space-grotesk/raw/master/fonts/ttf/SpaceGrotesk-Bold.ttf" -o SpaceGrotesk-Bold.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-Regular.ttf" -o DMSans-Regular.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-Medium.ttf" -o DMSans-Medium.ttf
curl -sL "https://github.com/googlefonts/dm-fonts/raw/master/Sans/Exports/DMSans-SemiBold.ttf" -o DMSans-SemiBold.ttf
```

Without these, the app falls back to system fonts.
