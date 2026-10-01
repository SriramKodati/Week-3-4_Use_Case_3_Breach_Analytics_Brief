import { Card } from "../components";

export default function ComingSoon({ feature, day }) {
  return (
    <Card interactive={false}>
      <p className="coming-soon">
        {feature} is scheduled for Week 4 {day}, per the build plan agreed at the design gate.
        Not built yet — this is not a bug.
      </p>
    </Card>
  );
}
