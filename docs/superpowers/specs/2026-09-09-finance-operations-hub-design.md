# Finance Operations Hub Design

**Date:** September 9, 2026  
**Status:** Approved for implementation

## Purpose

Turn the existing Daily Deposit application into a single Finance Operations Hub where a user first chooses which finance program to open. The Hub must preserve the finished Daily Deposit workflow while creating clear, isolated places for Credit Card Process and AP Statements.

## Goals

- Present one simple program-selection screen when a new browser session opens.
- Keep Daily Deposits fully available with its current behavior and appearance.
- Show Credit Card Process and AP Statements as polished Coming Soon programs.
- Let users return to the Hub without losing unfinished Daily Deposit entries.
- Keep future programs isolated so changes in one program do not break another.

## Non-Goals

- Build the Credit Card Process workflow in this phase.
- Build the AP Statements workflow in this phase.
- Redesign the Daily Deposit workflow.
- Add dashboards, reporting metrics, authentication, or permissions.
- Move the existing Daily Deposit engine into a different repository.

## Home Screen

The Hub uses the approved Program Cards layout.

### Header

- Honest Weight Food Co-op
- Finance Operations
- A Need Help action in the upper-right

### Main prompt

The page asks, “What are you working on?” and follows with “Choose a program to begin.” No dashboard statistics or unrelated controls appear on this screen.

### Program cards

1. **Daily Deposits**
   - Active card with the primary green emphasis.
   - Description: reconcile daily reports and prepare the QuickBooks import.
   - Action: “Open program →”.

2. **Credit Card Process**
   - Disabled, visually quieter card.
   - Short description of the future workflow.
   - Status: “Coming Soon”.

3. **AP Statements**
   - Disabled, visually quieter card.
   - Short description of the future workflow.
   - Status: “Coming Soon”.

On narrow screens, the three cards stack vertically and remain fully readable.

## Navigation Behavior

- A fresh Streamlit browser session opens on the Operations Hub.
- Selecting Daily Deposits stores the selected program in Streamlit session state and opens the existing workflow.
- Normal Streamlit reruns and browser refreshes within the same session keep the selected program open.
- Daily Deposits includes a clear “← All Programs” action near the top.
- “← All Programs” returns to the Hub without clearing Daily Deposit session data.
- Reopening Daily Deposits restores the in-progress entries from that session.
- The existing “Start Over” action remains the only control that clears Daily Deposit work. It does not return to the Hub.
- Unknown, removed, or malformed program selections fall back safely to the Hub.

## Help and Run History

- The Hub exposes a concise Need Help action in the header.
- The complete Daily Workbook SOP and Tips & Known Exceptions remain in their current location inside Daily Deposits.
- Daily Deposit Run History keeps its existing collapsed sidebar behavior when Daily Deposits is open.
- The Hub does not add a new dashboard or duplicate Daily Deposit help content.

## Technical Structure

Create a focused Hub UI module responsible for:

- Defining the available programs and their availability.
- Normalizing the selected-program session value.
- Rendering the Hub header and program cards.
- Returning the chosen program to the application entry point.
- Rendering the “All Programs” navigation action for an open program.

The application entry point calls the Hub routing layer before the existing Daily Deposit interface. When no active program is selected, it renders the Hub and stops the remainder of that Streamlit run. When Daily Deposits is selected, the existing Daily Deposit code continues to execute.

This phase deliberately avoids extracting or rewriting the finished Daily Deposit workflow. Future Credit Card Process and AP Statements implementations will be added as separate program modules behind the same routing boundary.

## State and Data Safety

- Program navigation uses a dedicated session-state key separate from all Daily Deposit keys.
- Returning to the Hub changes only the selected-program key.
- Daily Deposit uploads, breakdowns, reconciliation inputs, completion state, and generated-result state remain untouched by Hub navigation.
- Start Over continues to use the existing Daily Deposit reset logic.
- Coming Soon cards cannot create an active-program state.
- The router accepts only known enabled program identifiers.

## Error Handling

- Invalid program identifiers return the user to the Hub.
- A disabled program cannot be opened through the card UI.
- The Hub contains no file processing, accounting logic, or QuickBooks generation logic.
- A Hub rendering error must not mutate Daily Deposit data.

## Testing

Add automated coverage for:

- A fresh session showing the Hub.
- The Daily Deposits card being enabled.
- Credit Card Process and AP Statements displaying Coming Soon and remaining disabled.
- Selecting Daily Deposits opening the existing workflow.
- Returning to All Programs without clearing Daily Deposit state.
- Reopening Daily Deposits with prior session values intact.
- Invalid program selections returning to the Hub.
- Responsive card layout and required accessibility labels.
- Preservation of the existing Daily Deposit header, help, history, reset, and workflow wiring.

Run the full existing regression suite after implementation. No accounting, workbook parsing, mapping, reconciliation, or IIF-generation behavior may change in this phase.

## Delivery Sequence

1. Add tests for program definitions, routing state, and Hub rendering.
2. Add the isolated Hub UI module.
3. Gate the existing Daily Deposit screen behind the selected program.
4. Add the All Programs action without changing Start Over.
5. Verify responsive styling and accessibility.
6. Run the complete regression suite and review the final diff for Daily Deposit regressions.
