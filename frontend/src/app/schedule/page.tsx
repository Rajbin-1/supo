"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  Calendar,
  Clock,
  Youtube,
  Instagram,
  Send,
  Trash2,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Play,
  ArrowLeft,
  ExternalLink,
  RefreshCw,
  Sliders,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface ClipItem {
  id: string;
  task_id: string;
  hook_title?: string;
  hook_type?: string;
  virality_score: number;
  duration: number;
  text?: string;
  file_path: string;
  created_at: string;
}

interface ScheduledPost {
  id: string;
  clip_id?: string;
  clip_path: string;
  platform: string;
  title?: string;
  caption?: string;
  hashtags?: string[];
  scheduled_at: string;
  status: "queued" | "publishing" | "published" | "failed";
  published_url?: string;
  error_message?: string;
  created_at: string;
}

interface ClipScheduleConfig {
  selected: boolean;
  platform: "youtube" | "instagram";
  title: string;
  caption: string;
  tags: string;
  isGeneratingAI: boolean;
}

export default function SchedulePage() {
  const searchParams = useSearchParams();
  const preselectedClipId = searchParams.get("clip_id");

  const [activeTab, setActiveTab] = useState<"batch" | "queue">("batch");
  const [clips, setClips] = useState<ClipItem[]>([]);
  const [queue, setQueue] = useState<ScheduledPost[]>([]);
  const [isLoadingClips, setIsLoadingClips] = useState(true);
  const [isLoadingQueue, setIsLoadingQueue] = useState(false);

  // Scheduler parameters
  const [startTime, setStartTime] = useState<string>(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() + 15);
    return now.toISOString().slice(0, 16);
  });
  const [intervalHours, setIntervalHours] = useState<number>(3);
  const [configs, setConfigs] = useState<Record<string, ClipScheduleConfig>>({});
  const [isSubmittingBatch, setIsSubmittingBatch] = useState(false);
  const [notification, setNotification] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Load clips from database
  const loadClips = async () => {
    setIsLoadingClips(true);
    try {
      const res = await fetch("/api/schedule/clips");
      if (res.ok) {
        const data = await res.json();
        const loadedClips: ClipItem[] = data.clips || [];
        setClips(loadedClips);

        // Initialize configs for each clip
        const initialConfigs: Record<string, ClipScheduleConfig> = {};
        loadedClips.forEach((clip, index) => {
          const isPreselected = preselectedClipId === clip.id;
          initialConfigs[clip.id] = {
            selected: isPreselected || index === 0,
            platform: "youtube",
            title: clip.hook_title || "Viral Stream Moment",
            caption: clip.hook_title ? `Wait for the ending... ${clip.hook_title} 💀` : "",
            tags: "#shorts #viral #gaming",
            isGeneratingAI: false,
          };
        });
        setConfigs(initialConfigs);
      }
    } catch (e) {
      console.error("Error loading clips:", e);
    } finally {
      setIsLoadingClips(false);
    }
  };

  // Load active scheduled posts queue
  const loadQueue = async () => {
    setIsLoadingQueue(true);
    try {
      const res = await fetch("/api/schedule/queue");
      if (res.ok) {
        const data = await res.json();
        setQueue(data.queue || []);
      }
    } catch (e) {
      console.error("Error loading queue:", e);
    } finally {
      setIsLoadingQueue(false);
    }
  };

  useEffect(() => {
    void loadClips();
    void loadQueue();
  }, []);

  // Generate AI copy with Gemini 3 Flash Preview for a clip
  const handleGenerateAIMetadata = async (clipId: string) => {
    const current = configs[clipId];
    if (!current) return;

    setConfigs((prev) => ({
      ...prev,
      [clipId]: { ...prev[clipId], isGeneratingAI: true },
    }));

    try {
      const res = await fetch("/api/schedule/generate-metadata", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clip_id: clipId }),
      });

      if (!res.ok) throw new Error("Metadata generation failed");
      const meta = await res.json();

      setConfigs((prev) => {
        const item = prev[clipId];
        const isYT = item.platform === "youtube";
        return {
          ...prev,
          [clipId]: {
            ...item,
            title: isYT ? meta.youtube_title : item.title,
            caption: isYT ? meta.youtube_description : meta.instagram_caption,
            tags: isYT ? meta.youtube_tags?.join(" ") : meta.instagram_hashtags?.join(" "),
            isGeneratingAI: false,
          },
        };
      });
    } catch (err: any) {
      console.error(err);
      setNotification({ type: "error", message: `AI copy generation failed: ${err.message}` });
      setConfigs((prev) => ({
        ...prev,
        [clipId]: { ...prev[clipId], isGeneratingAI: false },
      }));
    }
  };

  // Switch platform for a clip
  const handlePlatformChange = (clipId: string, platform: "youtube" | "instagram") => {
    setConfigs((prev) => ({
      ...prev,
      [clipId]: { ...prev[clipId], platform },
    }));
  };

  // Schedule All for Today
  const handleScheduleAllForToday = async () => {
    const selectedClips = clips.filter((c) => configs[c.id]?.selected);
    if (selectedClips.length === 0) {
      setNotification({ type: "error", message: "Please select at least one clip to schedule." });
      return;
    }

    setIsSubmittingBatch(true);
    setNotification(null);

    const items = selectedClips.map((clip) => {
      const cfg = configs[clip.id];
      const tagsList = cfg.tags
        .split(/\s+/)
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      return {
        clip_id: clip.id,
        clip_path: clip.file_path,
        platform: cfg.platform,
        title: cfg.title,
        caption: cfg.caption,
        hashtags: tagsList,
      };
    });

    try {
      const res = await fetch("/api/schedule/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          items,
          start_time: new Date(startTime).toISOString(),
          interval_hours: intervalHours,
          auto_stagger: true,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Batch scheduling failed");
      }

      setNotification({
        type: "success",
        message: `Successfully scheduled ${selectedClips.length} clips with staggered intervals for today!`,
      });
      await loadQueue();
      setActiveTab("queue");
    } catch (err: any) {
      setNotification({ type: "error", message: err.message || "Failed to schedule clips." });
    } finally {
      setIsSubmittingBatch(false);
    }
  };

  // Publish a post immediately
  const handlePublishNow = async (postId: string) => {
    try {
      const res = await fetch(`/api/schedule/${postId}/publish-now`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Immediate publish failed");
      }
      setNotification({ type: "success", message: "Post triggered for immediate publishing!" });
      await loadQueue();
    } catch (e: any) {
      setNotification({ type: "error", message: e.message });
    }
  };

  // Cancel / delete a post
  const handleCancelPost = async (postId: string) => {
    try {
      const res = await fetch(`/api/schedule/${postId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete post");
      setQueue((prev) => prev.filter((p) => p.id !== postId));
      setNotification({ type: "success", message: "Scheduled post removed from queue." });
    } catch (e: any) {
      setNotification({ type: "error", message: e.message });
    }
  };

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link
            href="/"
            className="mb-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" /> Back to Dashboard
          </Link>
          <h1 className="font-display text-2xl font-bold tracking-tight sm:text-3xl">
            $0-Cost Bulk Clip Auto-Scheduler
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Auto-generate viral copy with Gemini and stagger publishing for YouTube Shorts & Instagram Reels.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-2 rounded-xl border bg-muted/30 p-1">
          <Button
            size="sm"
            variant={activeTab === "batch" ? "default" : "ghost"}
            onClick={() => setActiveTab("batch")}
            className="gap-2"
          >
            <Sliders className="size-4" /> Schedule Batch ({clips.length})
          </Button>
          <Button
            size="sm"
            variant={activeTab === "queue" ? "default" : "ghost"}
            onClick={() => {
              setActiveTab("queue");
              void loadQueue();
            }}
            className="gap-2"
          >
            <Layers className="size-4" /> Publishing Queue ({queue.length})
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {notification && (
        <div
          className={`mb-6 flex items-center justify-between rounded-xl border p-4 text-sm ${
            notification.type === "success"
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              : "border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-400"
          }`}
        >
          <div className="flex items-center gap-2">
            {notification.type === "success" ? (
              <CheckCircle2 className="size-5 shrink-0" />
            ) : (
              <AlertCircle className="size-5 shrink-0" />
            )}
            <span>{notification.message}</span>
          </div>
          <button
            onClick={() => setNotification(null)}
            className="text-xs font-semibold uppercase hover:underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* TAB 1: BATCH SCHEDULER */}
      {activeTab === "batch" && (
        <div className="space-y-6">
          {/* Scheduling Configuration Bar */}
          <div className="rounded-2xl border bg-card p-5 shadow-sm">
            <h2 className="text-base font-semibold">Today's Publishing Parameters</h2>
            <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground">Start Publishing At</label>
                <div className="mt-1 flex items-center gap-2">
                  <Clock className="size-4 text-muted-foreground" />
                  <Input
                    type="datetime-local"
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    className="h-9 text-xs"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-muted-foreground">Interval Between Posts</label>
                <div className="mt-1 flex items-center gap-2">
                  <Calendar className="size-4 text-muted-foreground" />
                  <select
                    value={intervalHours}
                    onChange={(e) => setIntervalHours(parseFloat(e.target.value))}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 text-xs"
                  >
                    <option value={1}>Every 1 hour (Fast viral pacing)</option>
                    <option value={2}>Every 2 hours</option>
                    <option value={3}>Every 3 hours (Optimal engagement)</option>
                    <option value={4}>Every 4 hours</option>
                    <option value={6}>Every 6 hours</option>
                  </select>
                </div>
              </div>

              <div className="flex items-end">
                <Button
                  onClick={handleScheduleAllForToday}
                  disabled={isSubmittingBatch || clips.filter((c) => configs[c.id]?.selected).length === 0}
                  className="h-9 w-full gap-2 bg-gradient-to-r from-purple-600 to-indigo-600 font-semibold text-white hover:from-purple-700 hover:to-indigo-700"
                >
                  <Send className="size-4" />
                  {isSubmittingBatch ? "Scheduling..." : "Schedule All for Today"}
                </Button>
              </div>
            </div>
          </div>

          {/* Clips List */}
          {isLoadingClips ? (
            <div className="py-12 text-center text-sm text-muted-foreground">Loading rendered clips...</div>
          ) : clips.length === 0 ? (
            <div className="rounded-2xl border border-dashed py-16 text-center">
              <p className="text-sm font-medium">No rendered clips found.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Run a clipping task from the home page to populate clips here.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>Select clips below to queue into today's staggered slots.</span>
                <span>
                  {clips.filter((c) => configs[c.id]?.selected).length} of {clips.length} selected
                </span>
              </div>

              {clips.map((clip, index) => {
                const cfg = configs[clip.id] || {
                  selected: false,
                  platform: "youtube",
                  title: "",
                  caption: "",
                  tags: "",
                  isGeneratingAI: false,
                };

                // Calculate preview slot time
                const baseDate = new Date(startTime);
                const slotDate = new Date(baseDate.getTime() + index * intervalHours * 3600 * 1000);
                const slotTimeStr = slotDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

                return (
                  <div
                    key={clip.id}
                    className={`rounded-2xl border p-5 transition-all ${
                      cfg.selected
                        ? "border-primary/40 bg-card shadow-sm"
                        : "border-border/60 bg-muted/10 opacity-70"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      {/* Left: Checkbox & Info */}
                      <div className="flex items-start gap-3">
                        <input
                          type="checkbox"
                          checked={cfg.selected}
                          onChange={(e) =>
                            setConfigs((prev) => ({
                              ...prev,
                              [clip.id]: { ...prev[clip.id], selected: e.target.checked },
                            }))
                          }
                          className="mt-1 size-4 rounded border-border"
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-sm">
                              {clip.hook_title || `Clip #${index + 1}`}
                            </span>
                            <Badge variant="secondary" className="text-[10px]">
                              Virality {clip.virality_score}/100
                            </Badge>
                            <span className="text-xs text-muted-foreground">{clip.duration.toFixed(1)}s</span>
                          </div>

                          <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant="outline" className="text-[10px]">
                              Slot #{index + 1}: {slotTimeStr}
                            </Badge>
                            <span className="truncate max-w-[280px] font-mono text-[10px]">
                              {clip.file_path}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Right: Platform Select & AI Button */}
                      <div className="flex items-center gap-2">
                        <div className="flex rounded-lg border bg-muted/40 p-0.5 text-xs">
                          <button
                            type="button"
                            onClick={() => handlePlatformChange(clip.id, "youtube")}
                            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors ${
                              cfg.platform === "youtube"
                                ? "bg-red-500/15 font-semibold text-red-600 dark:text-red-400"
                                : "text-muted-foreground"
                            }`}
                          >
                            <Youtube className="size-3.5" /> Shorts
                          </button>
                          <button
                            type="button"
                            onClick={() => handlePlatformChange(clip.id, "instagram")}
                            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors ${
                              cfg.platform === "instagram"
                                ? "bg-pink-500/15 font-semibold text-pink-600 dark:text-pink-400"
                                : "text-muted-foreground"
                            }`}
                          >
                            <Instagram className="size-3.5" /> Reels
                          </button>
                        </div>

                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleGenerateAIMetadata(clip.id)}
                          disabled={cfg.isGeneratingAI}
                          className="h-8 gap-1.5 text-xs"
                        >
                          <Sparkles className="size-3 text-purple-500" />
                          {cfg.isGeneratingAI ? "Writing Copy..." : "AI Generate Copy"}
                        </Button>
                      </div>
                    </div>

                    {/* Metadata Inputs */}
                    {cfg.selected && (
                      <div className="mt-4 grid grid-cols-1 gap-3 rounded-xl border bg-muted/20 p-3 sm:grid-cols-2">
                        {cfg.platform === "youtube" ? (
                          <>
                            <div className="sm:col-span-2">
                              <div className="flex items-center justify-between text-xs text-muted-foreground">
                                <label>Shorts Title (Curiosity-driven)</label>
                                <span className={cfg.title.length > 60 ? "text-amber-500" : ""}>
                                  {cfg.title.length}/60 chars
                                </span>
                              </div>
                              <Input
                                value={cfg.title}
                                onChange={(e) =>
                                  setConfigs((prev) => ({
                                    ...prev,
                                    [clip.id]: { ...prev[clip.id], title: e.target.value },
                                  }))
                                }
                                placeholder="Curiosity title under 60 chars"
                                className="mt-1 h-8 text-xs font-medium"
                              />
                            </div>

                            <div>
                              <label className="text-xs text-muted-foreground">Description (1-sentence payoff)</label>
                              <Input
                                value={cfg.caption}
                                onChange={(e) =>
                                  setConfigs((prev) => ({
                                    ...prev,
                                    [clip.id]: { ...prev[clip.id], caption: e.target.value },
                                  }))
                                }
                                placeholder="1-sentence description"
                                className="mt-1 h-8 text-xs"
                              />
                            </div>

                            <div>
                              <label className="text-xs text-muted-foreground">Tags (3 tags)</label>
                              <Input
                                value={cfg.tags}
                                onChange={(e) =>
                                  setConfigs((prev) => ({
                                    ...prev,
                                    [clip.id]: { ...prev[clip.id], tags: e.target.value },
                                  }))
                                }
                                placeholder="#shorts #topic #gaming"
                                className="mt-1 h-8 text-xs"
                              />
                            </div>
                          </>
                        ) : (
                          <>
                            <div className="sm:col-span-2">
                              <label className="text-xs text-muted-foreground">Reels Caption (2-line hook)</label>
                              <textarea
                                value={cfg.caption}
                                rows={2}
                                onChange={(e) =>
                                  setConfigs((prev) => ({
                                    ...prev,
                                    [clip.id]: { ...prev[clip.id], caption: e.target.value },
                                  }))
                                }
                                placeholder="Engaging hook caption..."
                                className="mt-1 w-full rounded-md border border-input bg-background p-2 text-xs"
                              />
                            </div>

                            <div className="sm:col-span-2">
                              <label className="text-xs text-muted-foreground">Niche Hashtags (3-5 tags)</label>
                              <Input
                                value={cfg.tags}
                                onChange={(e) =>
                                  setConfigs((prev) => ({
                                    ...prev,
                                    [clip.id]: { ...prev[clip.id], tags: e.target.value },
                                  }))
                                }
                                placeholder="#creator #streamer #highlight"
                                className="mt-1 h-8 text-xs"
                              />
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: LIVE PUBLISHING QUEUE */}
      {activeTab === "queue" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Active Daily Publishing Queue</h2>
            <Button size="sm" variant="outline" onClick={loadQueue} disabled={isLoadingQueue} className="gap-1.5 text-xs">
              <RefreshCw className={`size-3.5 ${isLoadingQueue ? "animate-spin" : ""}`} /> Refresh Queue
            </Button>
          </div>

          {queue.length === 0 ? (
            <div className="rounded-2xl border border-dashed py-16 text-center">
              <p className="text-sm font-medium">No posts in the publishing queue.</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Switch to the "Schedule Batch" tab to queue your clips for today.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {queue.map((post) => {
                const dateObj = new Date(post.scheduled_at);
                const timeStr = dateObj.toLocaleDateString([], {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                });

                return (
                  <div
                    key={post.id}
                    className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-4 shadow-sm"
                  >
                    <div className="flex items-center gap-3">
                      {post.platform === "youtube" ? (
                        <div className="flex size-9 items-center justify-center rounded-lg bg-red-500/10 text-red-600 dark:text-red-400">
                          <Youtube className="size-5" />
                        </div>
                      ) : (
                        <div className="flex size-9 items-center justify-center rounded-lg bg-pink-500/10 text-pink-600 dark:text-pink-400">
                          <Instagram className="size-5" />
                        </div>
                      )}

                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">{post.title || post.caption || "Clip"}</span>
                          <Badge
                            variant={
                              post.status === "published"
                                ? "default"
                                : post.status === "failed"
                                ? "destructive"
                                : post.status === "publishing"
                                ? "secondary"
                                : "outline"
                            }
                            className="text-[10px] capitalize"
                          >
                            {post.status}
                          </Badge>
                        </div>
                        <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Clock className="size-3" /> {timeStr}
                          </span>
                          <span className="truncate max-w-[200px] font-mono text-[10px]">{post.clip_path}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {post.published_url && (
                        <Button size="sm" variant="outline" asChild className="h-8 gap-1.5 text-xs text-emerald-600">
                          <a href={post.published_url} target="_blank" rel="noopener noreferrer">
                            <ExternalLink className="size-3.5" /> View Post
                          </a>
                        </Button>
                      )}

                      {post.status === "queued" && (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => handlePublishNow(post.id)}
                          className="h-8 gap-1.5 text-xs"
                        >
                          <Play className="size-3" /> Publish Now
                        </Button>
                      )}

                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleCancelPost(post.id)}
                        className="h-8 px-2 text-rose-500 hover:bg-rose-500/10"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </main>
  );
}
