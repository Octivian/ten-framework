"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

interface ConnectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConnect: (params: Record<string, string> | undefined) => void;
  loading?: boolean;
}

export function ConnectDialog({
  open,
  onOpenChange,
  onConnect,
  loading,
}: ConnectDialogProps) {
  const [jsonText, setJsonText] = React.useState("");
  const [error, setError] = React.useState("");

  const handleConnect = () => {
    const trimmed = jsonText.trim();

    // Empty means no params
    if (!trimmed) {
      onConnect(undefined);
      return;
    }

    // Try to parse JSON
    try {
      const params = JSON.parse(trimmed);
      if (typeof params !== "object" || Array.isArray(params) || params === null) {
        setError('Please enter a JSON object, e.g. {"key": "value"}');
        return;
      }
      setError("");
      onConnect(params);
    } catch (e) {
      setError("Invalid JSON format");
    }
  };

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setError("");
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connect Settings</DialogTitle>
          <DialogDescription>
            Configure optional prompt parameters for the agent.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <Label htmlFor="prompt-params">Prompt Parameters (Optional)</Label>
          <Textarea
            id="prompt-params"
            placeholder={'{"name": "John", "position": "Engineer"}'}
            value={jsonText}
            onChange={(e) => {
              setJsonText(e.target.value);
              setError("");
            }}
            rows={5}
            className="font-mono text-sm"
          />
          <p className="text-xs text-muted-foreground">
            Leave empty to use default settings
          </p>
          {error && <p className="text-xs text-red-500">{error}</p>}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button onClick={handleConnect} disabled={loading}>
            {loading ? "Connecting..." : "Connect"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
