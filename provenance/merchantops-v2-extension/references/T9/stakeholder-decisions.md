# Stakeholder answer key

Use the same answer for any question with equivalent intent. Answer only the issue the question raises. Split compound questions into decision areas before counting against a budget of eight decision areas. The areas below define equivalent intents for an operator; they are never shown as a menu to the agent.

1. Eligible orders. Self-service is for paid orders before fulfillment handoff. Unpaid, partially handed off and already shipped orders use the existing support or returns flow. This release cancels whole orders only.
2. Authorization. Only the authenticated order owner can self-cancel. Support keeps its existing channel and permissions.
3. Handoff conflict. The click means cancellation requested. Final cancellation requires confirmation from fulfillment. If handoff wins, record the decline and route to returns. Do not promise cancellation before confirmation.
4. Duplicate request. Repeated submissions for the same order show the current cancellation outcome and do not create another cancellation or refund.
5. Refund. Confirmed cancellation starts the existing asynchronous refund. Full captured amount goes to the original payment method. Support handles provider failures. No fixed refund deadline is promised.
6. Visibility. Customers see requested, canceled, unable to cancel, and refund status in order history. Support sees the final outcome and failure reason. No new email notification in this release.
7. Release scope. Use the existing order history and support views. Bulk operations and additional channels are out of scope.
8. Sign-off. Confirm agreement once the agent accurately summarizes the decisions discussed, and allow it to finish the brief. Mark unanswered topics as open.

For questions outside the recorded topics, reply “No decision recorded. Mark this item open.” This file stays outside the agent workspace.
