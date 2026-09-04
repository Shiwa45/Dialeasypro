# Getting your WhatsApp ads into the CRM — client guide

When someone clicks **WhatsApp** on your Facebook or Instagram ad and sends a
message, this creates a lead in your CRM automatically — with the ad they came
from attached. Your customer fills in **nothing**.

This is a one-time setup. Budget about an hour, plus Meta's review time for
business verification (a few days, and it can be started in parallel).

You will need: admin access to your company's Meta Business account, the
Facebook Page you advertise from, and **a phone number that is not currently
using WhatsApp or WhatsApp Business** — Meta requires a fresh number for a
business API account. Getting a new SIM for this is normal and recommended.

> Meta redesigns these screens often. Where a menu name has moved, look for the
> wording described rather than an exact path — the names of the *things* you
> need (Phone number ID, System user, Verify token) are stable even when the
> menus are not.

---

### 1. Sign in to Meta Business

Go to **business.facebook.com** and sign in. If your company has no Business
portfolio yet, create one with your real registered business name.

### 2. Find your Facebook Page

In your Business portfolio, confirm you can see the Page you run ads from.
This must be the same Page that will run the WhatsApp ads.

### 3. Set up your WhatsApp Business Account

In Business settings, look for **WhatsApp accounts** (sometimes under
*Accounts*). Add your business phone number here.

Remember: the number must not be registered on the normal WhatsApp app or the
WhatsApp Business app. If it is, remove it there first — and be aware that
deletes its existing chat history.

### 4. Open Meta for Developers

Go to **developers.facebook.com**, sign in with the same account, and open
**My Apps**.

### 5. Create the app

**Create app** → choose the **Business** type → give it a name your team will
recognise (e.g. "Acme CRM WhatsApp") → link it to your Business portfolio.

### 6. Add WhatsApp to the app

On the app's dashboard, find **WhatsApp** in the product list and add it.
Connect it to the WhatsApp Business Account from step 3.

### 7. Collect the four values the CRM needs

Copy these into a temporary note — you will paste them into the CRM in step 10.

| Value | Where to find it |
|---|---|
| **App ID** | App settings → Basic |
| **App Secret** | App settings → Basic → *Show* (treat as a password) |
| **Phone number ID** | WhatsApp → API Setup — a long number, **not** your phone number |
| **WhatsApp Business Account ID** | WhatsApp → API Setup |

### 8. Finish setting up the phone number

In WhatsApp → API Setup (or WhatsApp Manager), register your production number:
verify it by SMS or call, set the **display name** customers will see, and set a
**two-step PIN**. Meta reviews the display name — it must reflect your real
business name.

### 9. Create a permanent access token

The token shown on the API Setup page expires in 24 hours. For live use, create
one that does not:

Business settings → **Users** → **System users** → add a system user →
give it admin access to your app and your WhatsApp Business Account →
**Generate new token**.

Tick these permissions:

- `whatsapp_business_messaging`
- `whatsapp_business_management`
- `ads_read` — **optional but recommended.** Without it, leads still show which
  *ad* they came from, but the campaign, ad-set and ad **names** will be blank.

Copy the token immediately. Meta shows it once.

### 10. Enter everything in the CRM

In the CRM: **Settings → WhatsApp**.

1. Provider: **Meta Cloud API**
2. Paste the Access token, Phone number ID, WhatsApp Business Account ID and App
   secret
3. Click **Generate verify token** — copy the value it shows. It is displayed
   **once**; you need it in the next step.
4. Copy the **Webhook callback URL** shown on the same screen. It looks like
   `https://yourcompany.telecrm.in/api/v1/integrations/meta/whatsapp/`
5. Turn **Receive inbound messages** on, and save.

### 11. Point Meta at the CRM

Back in the app: **WhatsApp → Configuration → Webhook → Edit**.

- **Callback URL** — the URL from step 10.4
- **Verify token** — the token from step 10.3

Click **Verify and save**. It should confirm immediately. If it does not, see
[META_WHATSAPP_TROUBLESHOOTING.md](META_WHATSAPP_TROUBLESHOOTING.md) — the usual
cause is the verify token not being copied exactly.

### 12. Subscribe to messages

On the same Configuration screen there is a list of webhook fields with
**Manage** or **Subscribe** next to it. Tick **messages**.

**Do not skip this.** Step 11 succeeds without it, so everything looks finished
while nothing actually reaches the CRM. This one field carries incoming
messages, delivery receipts and the ad information.

### 13. Test with a real message

From your personal phone, send a WhatsApp to your business number — anything,
"hello" is fine.

### 14. Check the lead

Open the CRM's Leads list. Within a few seconds you should see a new lead with
your name, your number, source **WhatsApp**, and your message.

If it does not appear, stop here and work through the troubleshooting guide.
The ad test below cannot work until this does.

### 15. Run a Click-to-WhatsApp ad

In **Ads Manager**, create an ad whose goal sends people to **WhatsApp** (choose
the Engagement or Sales objective, then WhatsApp as the messaging destination),
select your Page and your WhatsApp number, and publish it.

It must be a genuinely published ad — a preview click does not produce ad data.

### 16. Check the attribution

From a phone that has **never** messaged your business number, click the ad and
send a message. Then open that lead in the CRM:

```
New Lead

Rahul Sharma
+91XXXXXXXXXX

Source:   Meta Click-to-WhatsApp
Channel:  WhatsApp

Campaign: Diwali Offer
Ad Set:   Delhi Audience
Ad:       Discount Ad

Message:
"Hi, I want more information."
```

Campaign, Ad Set and Ad lines appear **only** when your token has `ads_read`
(step 9). Without it you still get the ad reference and the ad's headline — the
CRM shows what Meta actually provided and leaves the rest blank rather than
displaying a name it cannot confirm.

---

## Things Meta controls, not the CRM

- **Business verification.** Meta reviews your company documents. Until it
  completes you are limited to a small number of conversations per day.
- **Display name approval.** Meta must approve the business name customers see.
- **Billing.** Add a payment method to the WhatsApp account — Meta charges per
  conversation, and messaging stops without one.
- **Number availability.** A number already on WhatsApp cannot be used until it
  is removed there.

## Good to know

- Someone who messages you twice does **not** become two leads. The second
  message is added to their existing lead's history.
- If an old lead marked *Lost* messages you again, they move back to **New** so
  your team sees them. A lead already marked won is left as it is.
- If the same person later clicks a **different** ad, the CRM starts a new
  conversation so each ad keeps its own honest attribution.
- Your access token, app secret and verify token are stored encrypted and are
  never shown again after saving — not in the CRM, not to your agents. If one is
  lost, generate a new one in Meta and re-enter it.
