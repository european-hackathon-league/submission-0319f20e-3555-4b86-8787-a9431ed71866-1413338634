"use client";

import type { ReactNode } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type PmSelectOption = {
  value: string;
  label: ReactNode;
  disabled?: boolean;
};

type PmSelectProps = {
  options: PmSelectOption[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  name?: string;
  id?: string;
  disabled?: boolean;
  required?: boolean;
  className?: string;
  "aria-label"?: string;
};

export function PmSelect({
  options,
  value,
  defaultValue,
  onValueChange,
  name,
  id,
  disabled,
  required,
  className,
  "aria-label": ariaLabel,
}: PmSelectProps) {
  return (
    <Select
      items={options}
      value={value}
      defaultValue={defaultValue}
      onValueChange={(next) => onValueChange?.(next ?? "")}
      name={name}
      id={id}
      disabled={disabled}
      required={required}
    >
      <SelectTrigger
        className={`pm-component-select ${className || ""}`}
        aria-label={ariaLabel}
      >
        <SelectValue
          placeholder={options.find((option) => option.value === "")?.label}
        />
      </SelectTrigger>
      <SelectContent
        className="pm-component-select-content"
        alignItemWithTrigger={false}
        align="start"
      >
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function PmMultiSelect({
  options,
  value,
  onValueChange,
  required,
  className,
  summary,
  "aria-label": ariaLabel,
}: {
  options: PmSelectOption[];
  value: string[];
  onValueChange: (value: string[]) => void;
  required?: boolean;
  className?: string;
  /** Trigger text for the current selection; defaults to the findings wording used by the decision form. */
  summary?: (selected: string[]) => string;
  "aria-label": string;
}) {
  return (
    <Select
      multiple
      items={options}
      value={value}
      onValueChange={onValueChange}
      required={required}
    >
      <SelectTrigger
        className={`pm-component-select ${className || ""}`}
        aria-label={ariaLabel}
      >
        <SelectValue>
          {(selected: string[]) =>
            summary
              ? summary(selected)
              : selected.length
              ? `${selected.length} ${selected.length === 1 ? "finding" : "findings"} selected`
              : "Select supporting findings"
          }
        </SelectValue>
      </SelectTrigger>
      <SelectContent
        className="pm-component-select-content"
        alignItemWithTrigger={false}
        align="start"
      >
        {options.map((option) => (
          <SelectItem
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
