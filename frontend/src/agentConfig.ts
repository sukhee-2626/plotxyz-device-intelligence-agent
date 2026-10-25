export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-device-intelligence-agent",
  "title": "Device Intelligence",
  "tagline": "Fit local AI to the machine you actually have.",
  "purpose": "Evaluates a user-supplied hardware profile against a catalog of local model sizes and recommends configurations that fit the available CPU, RAM, VRAM, and disk.",
  "accent": "#22d3ee",
  "features": [
    "Hardware compatibility scoring",
    "CPU-only versus accelerated guidance",
    "Constraint findings and ranked recommendations"
  ],
  "limitations": [
    "The model catalog is illustrative and must be checked against current model requirements.",
    "No system probing is performed; all inputs are user-supplied."
  ],
  "fields": [
    {
      "name": "hardware",
      "label": "Hardware profile (JSON)",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    },
    {
      "name": "use_case",
      "label": "Use case (coding, chat, speed, balanced)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "hardware": "{\"cpu_cores\": 8, \"ram_gb\": 16, \"vram_gb\": 6, \"disk_free_gb\": 120}",
    "use_case": "coding"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-device-intelligence-agent"
};
