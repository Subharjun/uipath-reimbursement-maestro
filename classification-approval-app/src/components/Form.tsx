import { useState, useEffect } from 'react';
import type { ChangeEvent } from 'react';
import { Theme } from '@uipath/coded-action-app';
import { codedActionAppService } from '../uipath';
import './Form.css';

// One property per field across all schema sections (inputs + outputs; inOuts is empty)
interface FormData {
  // inputs — read-only, from the classification stage.
  // riskScore/classificationConfidence arrive as STRINGS from the Case at runtime
  // (despite the numeric schema), so accept either and coerce when formatting.
  expenseType: string;
  riskScore: number | string;
  classificationConfidence: number | string;
  // outputs — reviewer-filled
  reviewerNotes: string;
}

const defaultFormData: FormData = {
  expenseType: '',
  riskScore: '',
  classificationConfidence: '',
  reviewerNotes: '',
};

const isDarkTheme = (theme: Theme): boolean =>
  theme === Theme.Dark || theme === Theme.DarkHighContrast;

interface FormProps {
  onInitTheme: (isDark: boolean) => void;
  darkTheme: boolean;
  onToggleTheme: () => void;
}

function Form({ onInitTheme, darkTheme, onToggleTheme }: FormProps) {
  const [formData, setFormData] = useState<FormData>(defaultFormData);
  const [isReadOnly, setIsReadOnly] = useState(false);

  useEffect(() => {
    codedActionAppService.getTask().then((task) => {
      // Merge over defaults — task.data has inputs + inOuts only, never outputs on first load.
      const merged = task.data
        ? { ...defaultFormData, ...(task.data as Partial<FormData>) }
        : defaultFormData;
      setFormData(merged);
      setIsReadOnly(task.isReadOnly);
      onInitTheme(isDarkTheme(task.theme));
    });
  }, [onInitTheme]);

  const handleTextChange = (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (isReadOnly) return;
    const { name, value } = e.target;
    const updated = { ...formData, [name]: value };
    setFormData(updated);
    codedActionAppService.setTaskData(updated);
  };

  // Notes are optional — the decision is valid as long as the task is editable.
  const isFormValid = !isReadOnly;

  const handleApprove = async () => {
    await codedActionAppService.completeTask('Approve', formData);
  };
  const handleReject = async () => {
    await codedActionAppService.completeTask('Reject', formData);
  };

  // Inputs may arrive as numbers or numeric strings — coerce before formatting.
  const toNumber = (raw: number | string) =>
    typeof raw === 'number' ? raw : parseFloat(String(raw).trim());

  // Stage 3 emits risk_score / classification_confidence as CATEGORICAL words
  // ("High" | "Medium" | "Low"), but the Case may instead pass numeric strings
  // ("0.85" / "3"). Render numbers numerically; otherwise show the raw label
  // as-is. Only a genuinely empty value collapses to '—'.
  const rawLabel = (raw: number | string) => {
    const s = String(raw).trim();
    return s.length ? s : '—';
  };

  // Confidence may arrive as 0-1 (model probability) or already as a percentage.
  const formatConfidence = (raw: number | string) => {
    const n = toNumber(raw);
    if (!Number.isFinite(n)) return rawLabel(raw);
    const pct = n > 0 && n <= 1 ? n * 100 : n;
    return `${pct.toFixed(0)}%`;
  };

  const formatRisk = (raw: number | string) => {
    const n = toNumber(raw);
    return Number.isFinite(n) ? String(n) : rawLabel(raw);
  };

  return (
    <div className="review-app">
      <header className="review-header">
        <div className="review-header__icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <path d="M14 2v6h6" />
            <path d="M9 15l2 2 4-4" />
          </svg>
        </div>
        <div className="review-header__titles">
          <h1 className="review-header__title">Reimbursement Classification Review</h1>
          <p className="review-header__subtitle">
            Review the AI classification, then approve or reject this reimbursement.
          </p>
        </div>
        <div className="review-header__actions">
          {isReadOnly && <span className="review-badge">Read only</span>}
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            aria-label={darkTheme ? 'Switch to light mode' : 'Switch to dark mode'}
            title={darkTheme ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {darkTheme ? (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </header>

      <div className="form-container form-container--enter">
        <section className="form-section">
          <h2 className="form-title">AI Classification</h2>
          <div className="form-grid">
            <div className="form-group">
              <label htmlFor="expenseType">Expense Type</label>
              <input id="expenseType" readOnly value={formData.expenseType} />
            </div>
            <div className="form-group">
              <label htmlFor="riskScore">Risk Score</label>
              <input id="riskScore" readOnly value={formatRisk(formData.riskScore)} />
            </div>
            <div className="form-group">
              <label htmlFor="classificationConfidence">Classification Confidence</label>
              <input
                id="classificationConfidence"
                readOnly
                value={formatConfidence(formData.classificationConfidence)}
              />
            </div>
          </div>
        </section>

        <section className="form-section">
          <h2 className="form-title">Reviewer Decision</h2>
          <div className="form-group form-group--spaced">
            <label htmlFor="reviewerNotes">Reviewer Notes</label>
            <textarea
              id="reviewerNotes"
              name="reviewerNotes"
              rows={5}
              placeholder="Optional — add a note explaining your decision…"
              value={formData.reviewerNotes}
              onChange={handleTextChange}
              readOnly={isReadOnly}
            />
          </div>
        </section>
      </div>

      <div className="form-buttons">
        <button
          type="button"
          className="outcome-btn outcome-btn--secondary"
          onClick={handleReject}
          disabled={!isFormValid}
        >
          Reject
        </button>
        <button
          type="button"
          className="outcome-btn outcome-btn--primary"
          onClick={handleApprove}
          disabled={!isFormValid}
        >
          Approve
        </button>
      </div>
    </div>
  );
}

export default Form;
