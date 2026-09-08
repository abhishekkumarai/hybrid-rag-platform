# Frontend Rules

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

1. Existing components already present in the project
2. shadcn/ui
3. 21st.dev-style components and patterns
4. Radix primitives
5. Custom components only when necessary

Do not recreate standard UI components from scratch.

Use shadcn/ui as the base component system.

For any component that needs stronger visual design,
look for an appropriate existing component from 21st.dev
rather than designing one from scratch.

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

Use Lucide icons or the project's existing icon system.

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

Never declare the frontend finished immediately after writing JSX.

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

## Important

Do not redesign the entire product when implementing a feature.

Preserve existing:

* information architecture
* workflows
* navigation
* branding

Improve visual quality without creating unnecessary architectural changes.
