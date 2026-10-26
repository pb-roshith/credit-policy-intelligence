import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import type { SecurityQuestionResponse } from "@/lib/auth";

const CUSTOM_QUESTION = "__custom_security_question__";

export function SecurityQuestionFields({
  responses,
  options,
  onChange,
  questionsReadOnly = false,
  allowCustomQuestions = true,
}: {
  responses: SecurityQuestionResponse[];
  options: string[];
  onChange: (index: number, field: keyof SecurityQuestionResponse, value: string) => void;
  questionsReadOnly?: boolean;
  allowCustomQuestions?: boolean;
}) {
  const [visibleAnswers, setVisibleAnswers] = useState<Record<number, boolean>>({});

  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-sm font-semibold">Security questions</legend>
      {responses.map((response, index) => {
        const usesCustomQuestion = !options.includes(response.question);
        const answerIsVisible = Boolean(visibleAnswers[index]);
        return (
          <div key={index} className="space-y-1.5">
            {questionsReadOnly ? (
              <p className="text-sm font-medium">
                {index + 1}. {response.question}
              </p>
            ) : (
              <>
                <select
                  required
                  aria-label={`Security question ${index + 1}`}
                  value={usesCustomQuestion ? CUSTOM_QUESTION : response.question}
                  onChange={(event) =>
                    onChange(
                      index,
                      "question",
                      event.target.value === CUSTOM_QUESTION ? "" : event.target.value,
                    )
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                >
                  {options.map((question) => (
                    <option
                      key={question}
                      value={question}
                      disabled={responses.some(
                        (other, otherIndex) => otherIndex !== index && other.question === question,
                      )}
                    >
                      {question}
                    </option>
                  ))}
                  {allowCustomQuestions && <option value={CUSTOM_QUESTION}>Custom question</option>}
                </select>
                {usesCustomQuestion && allowCustomQuestions && (
                  <input
                    required
                    minLength={5}
                    maxLength={256}
                    value={response.question}
                    onChange={(event) => onChange(index, "question", event.target.value)}
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                    placeholder="Type your custom security question"
                    aria-label={`Custom security question ${index + 1}`}
                  />
                )}
              </>
            )}
            <div className="relative">
              <input
                required
                minLength={2}
                maxLength={256}
                type={answerIsVisible ? "text" : "password"}
                autoComplete="off"
                value={response.answer}
                onChange={(event) => onChange(index, "answer", event.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 pr-10 text-sm outline-none focus:ring-2 focus:ring-ring"
                placeholder={`Answer ${index + 1}`}
                aria-label={`Answer to security question ${index + 1}`}
              />
              <button
                type="button"
                onClick={() =>
                  setVisibleAnswers((current) => ({
                    ...current,
                    [index]: !current[index],
                  }))
                }
                className="absolute right-0 top-0 flex h-10 w-10 items-center justify-center text-muted-foreground"
                aria-label={`${answerIsVisible ? "Hide" : "Show"} answer ${index + 1}`}
              >
                {answerIsVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
        );
      })}
      <p className="text-xs text-muted-foreground">
        Answers are not case-sensitive and are stored securely.
      </p>
    </fieldset>
  );
}
