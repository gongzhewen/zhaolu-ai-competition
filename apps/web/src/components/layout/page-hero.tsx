import type { ReactNode } from "react";

type PageHeroProps = {
  title: string;
  description: string;
  actions?: ReactNode;
};

export function PageHero({
  title,
  description,
  actions,
}: PageHeroProps) {
  return (
    <section className="page-command-hero">
      <div className="page-command-copy">
        <h1 className="page-title">{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {actions ? <div className="page-command-actions">{actions}</div> : null}
    </section>
  );
}
