import { cn } from "@/lib/utils";

type BrandLogoProps = {
  variant?: "full" | "mark";
  className?: string;
};

const SIZES = {
  full: { src: "/al-note-logo.png", width: 405, height: 332 },
  mark: { src: "/al-note-mark.png", width: 404, height: 237 },
} as const;

export function BrandLogo({ variant = "full", className }: BrandLogoProps) {
  const asset = SIZES[variant];
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={asset.src}
      alt="AL-Note"
      width={asset.width}
      height={asset.height}
      className={cn("object-contain", className)}
    />
  );
}
