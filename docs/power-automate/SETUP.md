# Power Automate weekday briefing flow

The application does not create or enable a Power Automate flow automatically. Set this up in the Microsoft tenant after an administrator has approved permissions, connection ownership and licensing. The instructions use Power Automate as the scheduler and Teams connector as the single delivery route. Do not also enable a backend Graph sender.

## Before setup

1. Deploy the API to a reachable HTTPS address; a local `localhost` API cannot be called by a cloud flow.
2. Store a long random automation shared token in the deployment secret store as `AUTOMATION_SHARED_TOKEN`. Set `AUTOMATION_USER_EMAIL` to the recipient’s signed-in app account.
3. Enable the API ingress only after HTTPS, authentication, rate limiting and monitoring are configured.
4. In a non-production environment, test the approved Teams connection and target direct chat. The Teams connector may have tenant licensing, environment and connection-owner requirements.
5. Ensure the recipient signs in to the application once so an application user record exists.

## Create the flow

1. Create a **Scheduled cloud flow**.
2. Set recurrence frequency to **Week**, interval **1**, and selected days **Monday, Tuesday, Wednesday, Thursday, Friday**.
3. Set start time to **06:55** and time zone to **(UTC+10:00) Canberra, Melbourne, Sydney**. Do not use a fixed UTC offset.
4. Add an HTTP action to `POST https://YOUR_API_HOST/api/v1/automation/briefings/run` with header `Authorization: Bearer <automation token from approved secure connection>`. Do not paste the token into exported flow documentation or screenshots. Prefer a secure input/connection reference maintained by the flow owner.
5. Parse the JSON response. Use `briefing_id`, `text`, `word_count` and `local_date`. Add a condition that `word_count` is less than 250. If false, do not send; invoke the failure path and alert the operator.
6. Add a Microsoft Teams action to post the `text` into the approved direct chat with the configured recipient. Use one connection and one direct-chat target. Keep only one Teams send action in the success path.
7. After successful post, call `POST https://YOUR_API_HOST/api/v1/automation/briefings/delivery` with the same bearer token and JSON body `{"briefing_id":"<response briefing_id>","status":"sent","reference":"<flow run or Teams message reference>"}`.
8. Configure failure scopes for the Teams send action. If it definitively fails, call the callback with status `failed`. If the action timed out and delivery is uncertain, call it with status `unknown`; do not blindly create a second send.
9. Add error notification to the approved administrator for failures of API generation, word-count validation, Teams send or callback. Do not include transcripts, message bodies or credentials.
10. Save the flow and restrict edit/run permissions to approved operators.

## Test the flow

- Use a non-production tenant and approved test chat.
- Run once manually and confirm the API returns a briefing under 250 words.
- Verify exactly one Teams message appears and callback status is `sent`.
- Replay the same run endpoint; it must return the same scheduled briefing for that Sydney-local date rather than generate a second delivery.
- Simulate a Teams failure and verify `failed` or `unknown` state is recorded without sending twice.
- Review flow run history around daylight-saving transition dates and confirm 06:55 Sydney local time.
- Rotate the automation secret through the hosting secret store and flow secure connection process.

## Limitations

Power Automate connector actions, authentication methods and licensing vary by tenant and can change. Validate the exact Teams action in the target tenant. The app cannot verify cloud-flow ownership or infer a successful Teams send until the callback is received. If a callback is lost, reconcile using the flow run ID/message record before retrying delivery.

