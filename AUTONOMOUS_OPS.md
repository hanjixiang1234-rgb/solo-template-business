## Autonomous Ops Model

### Goal

Run the account with minimal owner involvement.

The owner should not need to:
- write content
- choose topics
- schedule posts manually
- collect performance data manually
- decide daily execution details

### What I will own

I will handle:
- content direction
- topic selection
- script writing
- title and hook testing
- posting calendar
- data review
- iteration decisions
- backend offer planning

### What still requires the owner

Only platform-gated actions:
- initial account signup or handover
- phone verification
- QR code login when required
- real-name verification when required
- payout binding when monetization starts

### Recommended tool layer

Publishing and account management:
- `蚁小二`

Why:
- supports matrix management
- supports batch publishing
- supports app cloud publishing
- supports data statistics
- supports content publishing API and account management API

### Operating mode

1. Content production
- I maintain the topic queue, script files, and publishing sequence.

2. Scheduled publishing
- When the desktop is available, pending posts are pushed into Xiaohongshu native scheduling in advance.
- A local reconciler runs on login and at intervals so missed desktop time does not block future native-scheduled posts.

3. Data collection
- Performance data is reviewed on a recurring basis.

4. Optimization
- Weak hooks are rewritten.
- Strong topics are extended into series.
- Repeated audience questions become future products.

### Default phase-1 publishing model

- Platform: Xiaohongshu
- Format: image-plus-text notes first
- Frequency: 2 posts per day
- Content ratio:
  - 60 percent practical workflow posts
  - 30 percent monetization and systems posts
  - 10 percent offer-connection posts

### Working rule

The account should be treated as a dedicated work asset.
Do not use a personal everyday account for this project.

### Current execution model

- Phone-side or offline periods can queue intent, but Xiaohongshu posting still depends on the logged-in desktop browser profile.
- The desktop no longer needs to be online at the exact publish minute; it only needs to come online early enough to hand posts off to Xiaohongshu native scheduling.
- Local receipts live in `data/publish_runs.jsonl` and the queue state lives in `data/publish_queue.json`.

### Source notes

Verified on March 15, 2026:
- Ant Xiaoer official site: https://www.yxiaoer.cn/
- Ant Xiaoer open platform: https://open.yxiaoer.cn/

Observed capabilities from official pages:
- matrix management
- batch publishing
- account hosting
- data statistics
- content publishing API for video, image-text, and short content
- account management API
