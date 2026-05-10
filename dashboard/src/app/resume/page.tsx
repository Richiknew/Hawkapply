"use client";

import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchProfile, uploadResume } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Upload, User, Briefcase, GraduationCap, Code, Globe } from "lucide-react";
import { toast } from "sonner";

function SkillGroup({ title, skills }: { title: string; skills: string[] }) {
  if (!skills || skills.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {skills.map((s) => (
          <Badge key={s} variant="secondary" className="text-xs capitalize">
            {s}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export default function ResumePage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const { data: profile, isLoading, isError } = useQuery({
    queryKey: ["profile"],
    queryFn: fetchProfile,
  });

  const uploadMutation = useMutation({
    mutationFn: uploadResume,
    onSuccess: () => {
      toast.success("Resume uploaded and parsed!");
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function handleFile(file: File) {
    if (!file.name.endsWith(".pdf")) {
      toast.error("Only PDF files are supported");
      return;
    }
    uploadMutation.mutate(file);
  }

  const hasProfile = profile && Object.keys(profile).length > 0;

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold">Resume</h1>

      {/* Upload zone */}
      <Card
        className={`cursor-pointer border-2 border-dashed transition-colors ${
          dragging ? "border-primary bg-primary/5" : "border-border"
        }`}
        onClick={() => fileRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
      >
        <CardContent className="flex flex-col items-center gap-3 py-8">
          {uploadMutation.isPending ? (
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          ) : (
            <Upload className="h-8 w-8 text-muted-foreground" />
          )}
          <div className="text-center">
            <p className="font-medium">
              {uploadMutation.isPending ? "Parsing resume…" : "Drop PDF here or click to browse"}
            </p>
            <p className="text-sm text-muted-foreground">PDF only, max 10 MB</p>
          </div>
        </CardContent>
      </Card>

      <input
        ref={fileRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />

      {isLoading && (
        <div className="h-64 animate-pulse rounded-lg bg-muted" />
      )}

      {isError && (
        <p className="text-sm text-destructive">Failed to load profile.</p>
      )}

      {!isLoading && !isError && !hasProfile && (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground text-center">
            No resume parsed yet. Upload a PDF to get started.
          </CardContent>
        </Card>
      )}

      {hasProfile && (
        <div className="space-y-4">
          {/* Header */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <User className="h-4 w-4" />
                {profile.name ?? "Candidate"}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              {profile.email && <p>{profile.email}</p>}
              {profile.phone && <p>{profile.phone}</p>}
              {profile.location && <p className="text-muted-foreground">{profile.location}</p>}
              {profile.visa_status && (
                <Badge variant="outline" className="mt-1">{profile.visa_status}</Badge>
              )}
              {profile.years_experience != null && (
                <p className="text-muted-foreground">{profile.years_experience} years experience</p>
              )}
              <div className="flex flex-wrap gap-3 pt-1">
                {profile.linkedin && (
                  <a href={profile.linkedin} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-primary hover:underline">
                    <Globe className="h-3 w-3" /> LinkedIn
                  </a>
                )}
                {profile.github && (
                  <a href={profile.github} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-primary hover:underline">
                    <Globe className="h-3 w-3" /> GitHub
                  </a>
                )}
                {profile.portfolio && (
                  <a href={profile.portfolio} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-primary hover:underline">
                    <Globe className="h-3 w-3" /> Portfolio
                  </a>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Skills */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Code className="h-4 w-4" />
                Skills
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <SkillGroup title="Programming Languages" skills={profile.programming_languages ?? []} />
              <SkillGroup title="Tools & Platforms" skills={profile.tools_and_platforms ?? []} />
              <SkillGroup title="ML Techniques" skills={profile.ml_techniques ?? []} />
              <SkillGroup title="Domain Knowledge" skills={profile.domain_knowledge ?? []} />
              <SkillGroup title="Soft Skills" skills={profile.soft_skills ?? []} />
              {profile.certifications && profile.certifications.length > 0 && (
                <SkillGroup title="Certifications" skills={profile.certifications} />
              )}
            </CardContent>
          </Card>

          {/* Work Experience */}
          {profile.work_experience && profile.work_experience.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Briefcase className="h-4 w-4" />
                  Work Experience
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-5">
                {profile.work_experience.map((exp, i) => (
                  <div key={i} className={i > 0 ? "border-t pt-4" : ""}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-sm">{exp.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {exp.company}{exp.location ? ` · ${exp.location}` : ""}
                        </p>
                      </div>
                      {exp.dates && (
                        <span className="text-xs text-muted-foreground shrink-0">{exp.dates}</span>
                      )}
                    </div>
                    {exp.highlights && exp.highlights.length > 0 && (
                      <ul className="mt-2 space-y-1">
                        {exp.highlights.map((h, j) => (
                          <li key={j} className="text-xs text-muted-foreground flex gap-2">
                            <span className="shrink-0 mt-0.5">•</span>
                            <span>{h}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Education */}
          {profile.education && profile.education.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <GraduationCap className="h-4 w-4" />
                  Education
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {profile.education.map((edu, i) => (
                  <div key={i} className={i > 0 ? "border-t pt-3" : ""}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-semibold text-sm">{edu.degree}</p>
                        <p className="text-sm text-muted-foreground">
                          {edu.school}{edu.location ? ` · ${edu.location}` : ""}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        {edu.graduation && (
                          <p className="text-xs text-muted-foreground">{edu.graduation}</p>
                        )}
                        {edu.gpa != null && (
                          <p className="text-xs text-muted-foreground">GPA: {edu.gpa}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
