"use client";

import { JevSettings } from "@/components/settings/JevSettings";

export function Jev() {
  return (
    <div className="flex h-full w-full flex-col">
      <div className="p-6 max-w-6xl mx-auto w-full flex-1 overflow-y-auto">
        <JevSettings />
      </div>
    </div>
  );
}