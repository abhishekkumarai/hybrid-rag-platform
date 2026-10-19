# Frontend Rules

The client is the Flutter app in `app_flutter/` (web + Android/iOS), Evergreen light theme — tokens in
`app_flutter/lib/theme/evergreen_theme.dart`, spec and wireframes in `ui/stitch_workspace/`. Generic rules below
apply to any UI work; where they name web libraries (shadcn/ui, Lucide, JSX), read "the project's existing
widgets and icon set" instead. Do not add a second component system.

## Primary Goal

Build interfaces that look like a professionally designed production product.

Do NOT invent generic SaaS UI.

The frontend should feel:

* polished
* intentional
* modern
* consistent
* functional
* visually restrained

## Component Strategy

Use this order of preference:

1. Existing widgets in `app_flutter/lib/widgets/` and the feature folders
2. Material 3 widgets themed by `EvergreenTheme`
3. Custom widgets only when necessary

Do not recreate standard widgets from scratch, and do not hard-code colors: use the theme tokens.

Do not invent custom UI patterns unless necessary.

Keep the entire application visually consistent.

## Design Rules

Prefer:

* strong typography hierarchy
* consistent spacing
* subtle borders
* restrained shadows
* meaningful whitespace
* compact and useful controls
* clear primary actions
* consistent component sizing

Avoid:

* excessive rounded cards
* excessive shadows
* glassmorphism
* random gradients
* purple "AI" gradients
* giant headings
* unnecessary animations
* decorative blobs
* 3-column card grids by default
* too many badges
* excessive icons
* centered layouts everywhere
* generic dashboard templates

## Before Building a Page

First determine:

1. What is the user trying to accomplish?
2. What is the primary action?
3. What information is most important?
4. What information is secondary?
5. Which elements can be progressively disclosed?

Then design the hierarchy.

Do not immediately start creating cards and components.

## Layout

Use a consistent spacing system.

Prefer:

* max-width containers
* clear alignment
* consistent vertical rhythm
* responsive layouts
* dense layouts when the product requires scanning information

Do not add whitespace simply because it looks "modern."

## Typography

Use a professional sans-serif font.

Maintain a clear hierarchy between:

* page title
* section title
* body
* metadata
* labels

Do not use many different font weights or sizes without reason.

## Color

Use a restrained palette.

Default:

* neutral background
* high-contrast primary text
* muted secondary text
* one primary accent

Do not introduce multiple accent colors unless required by the product.

## Icons

Use the Material icon set the app already uses.

Do not use emojis as UI icons.

Do not add icons merely for decoration.

## Animation

Animations must communicate state or improve interaction.

Prefer subtle:

* opacity
* transform
* height
* scale

Avoid excessive animation.

## Responsive Design

Every page must work on:

* desktop
* tablet
* mobile

Do not treat mobile as an afterthought.

## Implementation Workflow

For every significant frontend task:

1. Inspect the existing application.
2. Reuse existing components.
3. Identify the page hierarchy.
4. Implement the structure.
5. Run the application.
6. Visually inspect the result.
7. Fix obvious visual problems.
8. Test responsive behavior.
9. Only then consider the task complete.

Never declare the frontend finished immediately after writing the widget code: run `make flutter-test` and look at it in `flutter run -d chrome`.

## Visual Quality Check

Before finishing, check:

* Is the hierarchy obvious?
* Is the primary action obvious?
* Are elements aligned?
* Is spacing consistent?
* Are there unnecessary cards?
* Are there unnecessary borders?
* Are there unnecessary icons?
* Does anything look like a generic AI-generated template?
* Does the page feel visually balanced?
* Does mobile still work?

When something can be simpler, make it simpler.

## Accounts and shared chats

* Every screen assumes a signed-in user; an unauthenticated request lands on `/signin` (`screens/signin`). Reuse its
  card and field styles for any future account forms.
* A `/s/<token>` shared chat is a separate read-only screen (`screens/shared`): no composer, settings or project
  controls, and the "Continue this chat" action is its single call to action.
* Content in a shared chat was written by someone else. Render it as text/markdown; never interpret it as HTML.
* Controls for admin-only operations (web sync, all-projects views, `features/admin`) are hidden or disabled for
  regular users.

## Parity checklist (IRA-52)

Behaviours the removed web page had, and where the Flutter client implements them:

* Sign-in, sign-up, "Try demo", sign-out: `screens/signin`.
* Project gallery, create/rename/delete projects: `features/workspace`, `screens/home`.
* Add sources (file, URL, crawl depth) with background progress: `screens/library`, `features/project`.
* Chat with streaming, mode and model selection, parameters: `features/chat`, `screens/settings`.
* Citation inspector with page preview, bbox highlight, rerank score: `screens/project/chat`.
* Per-project observability, evaluation and feedback views: `screens/observability`, `screens/evaluation`.
* Share link create/revoke, read-only viewer, fork: `screens/shared`.

## Important

Do not redesign the entire product when implementing a feature.

Preserve existing:

* information architecture
* workflows
* navigation
* branding

Improve visual quality without creating unnecessary architectural changes.
