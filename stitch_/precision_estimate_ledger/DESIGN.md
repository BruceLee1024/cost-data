---
name: Precision Estimate Ledger
colors:
  surface: '#f8f9fb'
  surface-dim: '#d9dadc'
  surface-bright: '#f8f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f6'
  surface-container: '#edeef0'
  surface-container-high: '#e7e8ea'
  surface-container-highest: '#e1e2e4'
  on-surface: '#191c1e'
  on-surface-variant: '#3f4944'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f3'
  outline: '#6f7973'
  outline-variant: '#bec9c2'
  surface-tint: '#1b6b51'
  primary: '#004532'
  on-primary: '#ffffff'
  primary-container: '#065f46'
  on-primary-container: '#8bd6b7'
  inverse-primary: '#8bd6b6'
  secondary: '#0058be'
  on-secondary: '#ffffff'
  secondary-container: '#2170e4'
  on-secondary-container: '#fefcff'
  tertiary: '#5e3000'
  on-tertiary: '#ffffff'
  tertiary-container: '#804300'
  on-tertiary-container: '#ffb87e'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#a6f2d1'
  primary-fixed-dim: '#8bd6b6'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#ffdcc3'
  tertiary-fixed-dim: '#ffb77d'
  on-tertiary-fixed: '#2f1500'
  on-tertiary-fixed-variant: '#6e3900'
  background: '#f8f9fb'
  on-background: '#191c1e'
  surface-variant: '#e1e2e4'
typography:
  h1:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  h2:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  data-mono:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  row-height: 36px
  sidebar-width: 260px
  drawer-width: 480px
  gutter: 16px
  margin-page: 24px
---

## Brand & Style

This design system is engineered for the rigorous demands of construction cost engineering and personal data management. The aesthetic is defined by **Professional Minimalism**, prioritizing information density and functional clarity over decorative flair. 

The design narrative is built around the "Data Workbench" concept—a digital environment that feels as reliable and precise as the physical tools used in engineering. It evokes an emotional response of organized control and professional authority. By utilizing a restrained color palette and a structured grid, the system minimizes cognitive load for users performing long-duration, high-concentration tasks. The visual language is strictly "Desktop-First," optimized for high-resolution monitors where complex data relationships need to be visible at a single glance.

## Colors

The color strategy is functional and hierarchical, adhering to WCAG 2.1 AA accessibility standards for all interactive elements.

- **Primary (#065F46):** A deep Emerald Green used for primary actions, active navigation states, and brand presence. It signifies stability and growth.
- **Background (#F3F4F6):** A cool neutral light grey serves as the canvas, reducing eye strain during extended data entry sessions.
- **Accents:** 
  - **Blue (#3B82F6):** Used for informational badges, links, and secondary selection states.
  - **Amber (#D97706):** Reserved for warning states, pending approvals, or items requiring attention.
  - **Red (#DC2626):** Strictly for destructive actions, errors, and high-priority discrepancies.
- **Neutral Scale:** Uses a range of greys from #F9FAFB (surface) to #111827 (text) to create subtle contrast between structural areas like sidebars and main content.

## Typography

The typography system prioritizes legibility and data alignment. **Inter** is used for all UI labels, navigation, and instructional text due to its exceptional clarity at small sizes. 

For all numeric values, quantities, and currency entries, **JetBrains Mono** is employed. This ensures that columns of numbers align perfectly, allowing cost engineers to scan for discrepancies or outliers vertically without visual "jitter."

- **Desktop Scale:** The base font size is set at 14px for body text, with 12px used for secondary metadata. 
- **Headings:** Reserved for page titles and section headers to maintain a clear information hierarchy.
- **Labels:** Small, uppercase labels with increased letter-spacing are used for table headers and form categories to differentiate them from user-generated content.

## Layout & Spacing

The layout utilizes a **Fixed-Fluid Hybrid** model optimized for wide-screen data management.

- **Main Navigation:** A vertical sidebar (260px) on the left provides access to the project tree and database categories.
- **Content Area:** A fluid center section that expands to fit the viewport.
- **Side Panels:** A right-aligned "Drawer" (480px) emerges for detailed viewing or editing of a specific line item without losing the context of the main list.
- **The 4px Grid:** All spacing is based on a 4px increment. High-density components utilize tighter padding (8px internal) to maximize the "above the fold" data visibility.
- **Table Density:** Rows are locked at 36px height, striking a balance between extreme density and touch/click accuracy.

## Elevation & Depth

This design system uses **Tonal Layering** and **Low-Contrast Outlines** rather than heavy shadows to signify depth, maintaining a flat, professional profile.

- **Level 0 (Background):** #F3F4F6 - The base application background.
- **Level 1 (Cards/Work Surface):** #FFFFFF - Primary content areas, tables, and whiteboards. These are defined by a 1px border (#E5E7EB) rather than a shadow.
- **Level 2 (Popovers/Dropdowns):** #FFFFFF with a 1px border and a very soft "Ambient Shadow" (0px 2px 4px rgba(0,0,0,0.05)).
- **Level 3 (Modals/Drawers):** These use a stronger backdrop dimming (overlay) to focus attention, but the containers themselves remain crisp with minimal 4px blur shadows.

## Shapes

To reinforce the sense of engineering precision, the shape language is **Strict and Geometric**. 

- **Corner Radius:** A maximum of 6px (`rounded-md`) is applied to cards and large containers. 
- **Small Elements:** Buttons, input fields, and tags use a 4px (`rounded-sm`) radius.
- **Buttons:** Sharp corners are avoided to ensure interactive elements are identifiable, but the radius never exceeds 4px to maintain the "professional tool" aesthetic.
- **Selection Indicators:** Active states in the sidebar or tree view use a 0px radius on the "inner" edge to create a seamless connection with the panel border.

## Components

### High-Density Tables
- **Row Height:** 36px.
- **Cell Padding:** 12px horizontal.
- **Typography:** Use `data-mono` for all numeric columns. 
- **Alignment:** Right-align currency and quantities; left-align text descriptions.
- **Borders:** 1px horizontal-only divider (#E5E7EB).

### Tree Structure
- Use a 16px indent per level.
- Use "Chevron" icons for expansion.
- Hover states should highlight the entire row width with #F9FAFB.

### Input Fields
- **Height:** 32px.
- **Border:** 1px solid #D1D5DB.
- **Focus State:** 1px solid #065F46 with a subtle 2px outer glow in the same color (20% opacity).

### Buttons
- **Primary:** Background #065F46, Text #FFFFFF.
- **Secondary:** Background #FFFFFF, Border 1px #D1D5DB, Text #374151.
- **Ghost:** No background or border, Text #6B7280, for tertiary actions in tables.

### Right Drawer
- Slides in from the right edge, covering the right 480px of the screen.
- Contains a header with a "Close" icon and the "Save" action pinned to the bottom.
- Uses a background blur on the main content to focus user attention.